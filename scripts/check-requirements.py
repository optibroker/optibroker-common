#!/usr/bin/env python3
"""Fail if any requirement is held below its latest release.

Run by `make requirements-check` on every pull request. A requirement is out
of date when its specifier does not admit the newest release on PyPI that
supports the repo's Python. That covers `==` pins that have fallen behind and
upper bounds such as `Werkzeug<3.0`; unpinned and `>=` lines always admit the
latest, so they pass. `pkg @ git+...@vX` is compared with the newest tag.

A release only becomes required once it has been on PyPI for 48 hours
(--min-age-hours, or $REQUIREMENTS_MIN_AGE_HOURS), so a bad or compromised
release has time to be yanked first. A pin on a newer, still-waiting release
also passes. `--update` moves to the newest release past the wait.

Deliberately strict after that: a release required since the last update
fails the next PR, and `make requirements-update` is the fix. In GitHub
Actions each finding is an error annotation on its line of the requirements
file, and a table in the job summary.

It also fails when requirements_test.txt pins something requirements.txt
rules out. The test image installs it second, so the tests would run against
a different version from the one that ships.

Could-not-check is never reported as up to date: a package PyPI does not
answer for fails the run with its own message, because a check that passes
when it cannot see is worse than no check.

    scripts/check-requirements.py                # check; exit 1 if behind
    scripts/check-requirements.py --update       # rewrite to the latest
    scripts/check-requirements.py --python 3.11  # override the Dockerfile

Standard library only, so CI runs it on the runner's Python with no build.
Canonical copy: optibroker-project-config/scripts/check-requirements.py.
"""
import argparse
import concurrent.futures
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

FILES = ("requirements.txt", "requirements_test.txt")
PYPI = os.environ.get("PYPI_JSON_URL", "https://pypi.org/pypi/{name}/json")
# A release is only required once it has been public this long, so a bad or
# compromised release has time to be yanked before every PR demands it.
MIN_AGE_HOURS = float(os.environ.get("REQUIREMENTS_MIN_AGE_HOURS", "48"))

LINE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?P<extras>\[[^\]]*\])?"
    r"\s*(?P<spec>[^;#]*?)"
    r"\s*(?P<marker>;[^#]*)?"
    r"\s*(?P<comment>#.*)?$")
GIT = re.compile(r"^@\s*git\+(?P<url>[^@\s]+?)(?:@(?P<ref>[^\s#;]+))?$")
CLAUSE = re.compile(r"^(===|==|!=|~=|<=|>=|<|>)\s*(\S+)$")
PRE = re.compile(r"(a|b|rc|alpha|beta|c|pre|preview|dev)\d*", re.I)


def say(text=""):
    sys.stdout.write(f"{text}\n")


def canonical(name):
    return re.sub(r"[-_.]+", "-", name).lower()


# -- versions ----------------------------------------------------------------
# A PEP 440 subset: release numbers, with pre-releases and dev releases marked
# so they are never chosen as "latest". Local versions and epochs are not
# used by anything on PyPI this estate depends on.
def parse_version(text):
    text = text.strip().lower().lstrip("v")
    m = re.match(r"^(\d+(?:\.\d+)*)(.*)$", text)
    if not m:
        return None
    release = tuple(int(p) for p in m.group(1).split("."))
    rest = m.group(2).lstrip(".-_")
    if rest.startswith("post"):
        rest = ""
    return release, bool(rest and PRE.match(rest))


def _pad(a, b):
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)), b + (0,) * (n - len(b))


def _cmp(a, b):
    a, b = _pad(a, b)
    return (a > b) - (a < b)


def _clause_ok(version, op, target):
    if target.endswith(".*"):
        prefix = tuple(int(p) for p in target[:-2].split("."))
        match = version[:len(prefix)] == prefix
        return match if op == "==" else not match
    parsed = parse_version(target)
    if not parsed:
        raise ValueError(f"cannot read version {target!r}")
    t = parsed[0]
    c = _cmp(version, t)
    if op == "~=":
        return c >= 0 and version[:len(t) - 1] == t[:len(t) - 1]
    return {"==": c == 0, "===": c == 0, "!=": c != 0, "<": c < 0,
            "<=": c <= 0, ">": c > 0, ">=": c >= 0}[op]


def satisfies(version, spec):
    """Does `version` (a release tuple) satisfy a specifier like >=1,<2?"""
    for clause in [c.strip() for c in spec.split(",") if c.strip()]:
        m = CLAUSE.match(clause)
        if not m:
            raise ValueError(f"cannot read specifier {clause!r}")
        if not _clause_ok(version, *m.groups()):
            return False
    return True


def fmt(release):
    return ".".join(str(p) for p in release)


# -- sources of "latest" -----------------------------------------------------
def _get_json(url, attempts=3):
    for i in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if i == attempts - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if i == attempts - 1:
                raise
        time.sleep(1 + i)
    return None


def _python_ok(requires, python):
    if not requires:
        return True
    try:
        return satisfies(python, requires)
    except ValueError:
        return True   # an unreadable requires_python is not this repo's fault


def _released_at(files):
    """When a release was published: its earliest file upload."""
    times = []
    for f in files:
        stamp = f.get("upload_time_iso_8601") or f.get("upload_time")
        if stamp:
            stamp = stamp.replace("Z", "+00:00")
            when = datetime.datetime.fromisoformat(stamp)
            if when.tzinfo is None:
                when = when.replace(tzinfo=datetime.timezone.utc)
            times.append(when)
    return min(times) if times else None


def pypi_latest(name, python, min_age_hours=0, now=None):
    """-> (required, required_text, newer).

    `required` is the newest non-yanked final release that installs on this
    Python and has been public for `min_age_hours`; `newer` lists the
    installable releases younger than that, which are accepted but not yet
    required. `required` is None when every release is still that young.
    """
    data = _get_json(PYPI.format(name=name))
    if data is None:
        raise LookupError(f"PyPI has no project named {name!r}")
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(hours=min_age_hours)
    best, newer, seen = None, [], False
    for text, files in data.get("releases", {}).items():
        parsed = parse_version(text)
        if not parsed or parsed[1]:
            continue
        live = [f for f in files if not f.get("yanked")]
        if not any(_python_ok(f.get("requires_python"), python)
                   for f in live):
            continue
        seen = True
        released = _released_at(live)
        if released is not None and released > cutoff:
            newer.append(parsed[0])
            continue
        if best is None or _cmp(parsed[0], best[0]) > 0:
            best = (parsed[0], text)
    if not seen:
        raise LookupError(
            f"no release of {name} supports Python {fmt(python)}")
    if best is None:
        return None, None, newer
    return best[0], best[1], [v for v in newer if _cmp(v, best[0]) > 0]


def git_latest(url):
    out = subprocess.run(["git", "ls-remote", "--tags", "--refs", url],
                         capture_output=True, text=True, timeout=60,
                         check=False)
    if out.returncode != 0:
        reason = out.stderr.strip()[:200]
        raise LookupError(f"cannot list tags of {url}: {reason}")
    best = None
    for line in out.stdout.splitlines():
        tag = line.rsplit("refs/tags/", 1)[-1]
        parsed = parse_version(tag)
        if not parsed or parsed[1]:
            continue
        if best is None or _cmp(parsed[0], best[0]) > 0:
            best = (parsed[0], tag)
    if best is None:
        raise LookupError(f"{url} has no version tags")
    return best[0], best[1], []


# -- requirements files ------------------------------------------------------
class Req:
    def __init__(self, path, index, raw, match):
        self.path, self.index, self.raw = path, index, raw
        self.name = match.group("name")
        self.extras = match.group("extras") or ""
        self.spec = (match.group("spec") or "").strip()
        self.marker = match.group("marker") or ""
        self.comment = match.group("comment") or ""
        self.git = GIT.match(self.spec) if self.spec.startswith("@") else None
        self.key = canonical(self.name)

    @classmethod
    def parse(cls, path, index, raw):
        line = raw.strip()
        m = LINE.match(line)
        if not m:
            raise ValueError(f"{path}:{index + 1}: cannot read {line!r}")
        return cls(path, index, raw, m)


def read_requirements(path):
    with open(path, encoding="utf-8", newline="") as f:
        lines = f.read().splitlines()
    return [Req.parse(path, i, raw) for i, raw in enumerate(lines)
            if raw.strip() and not raw.strip().startswith(("#", "-"))]


def detect_python(root):
    path = os.path.join(root, "Dockerfile")
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"\s*FROM\s+(?:\S+/)?python:(\d+)\.(\d+)",
                             line, re.I)
                if m:
                    return int(m.group(1)), int(m.group(2))
    return sys.version_info[:2]


# -- the check ---------------------------------------------------------------
class Finding:
    def __init__(self, req, latest, latest_text, problem):
        self.req, self.latest = req, latest
        self.latest_text, self.problem = latest_text, problem


def _lookup(key, python, min_age_hours):
    kind, ident = key
    try:
        if kind == "git":
            return key, git_latest(ident), None
        return key, pypi_latest(ident, python, min_age_hours), None
    except Exception as e:   # reported, never treated as up to date
        return key, None, f"{ident}: {e}"


def _source(req):
    return ("git", req.git.group("url")) if req.git else ("pypi", req.key)


def _behind(req, latest):
    required, text, newer = latest
    if required is None:
        return None   # every release is still inside the waiting period
    if req.git:
        ref = req.git.group("ref") or ""
        current = parse_version(ref)
        if not current or _cmp(current[0], required) < 0:
            problem = f"at {ref or 'default branch'}"
            return Finding(req, required, text, problem)
        return None
    # Admitting a newer, still-waiting release counts as current too.
    if req.spec and not any(satisfies(v, req.spec)
                            for v in [required, *newer]):
        return Finding(req, required, text, req.spec)
    return None


def check(reqs, python, workers=16, min_age_hours=MIN_AGE_HOURS):
    """-> (behind, errors); `errors` lists what could not be checked."""
    keys = list(dict.fromkeys(_source(r) for r in reqs))
    latest, errors = {}, []
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        lookups = pool.map(lambda k: _lookup(k, python, min_age_hours),
                           keys)
        for key, value, err in lookups:
            latest[key] = value
            if err:
                errors.append(err)

    behind = []
    for r in reqs:
        found = latest.get(_source(r))
        if found is None:
            continue
        try:
            finding = _behind(r, found)
        except ValueError as e:
            errors.append(f"{r.name}: {e}")
            continue
        if finding:
            behind.append(finding)
    return behind, errors


def _exact(spec):
    m = re.fullmatch(r"\s*===?\s*([0-9][^,\s*]*)\s*", spec or "")
    parsed = parse_version(m.group(1)) if m else None
    return parsed[0] if parsed else None


def _conflict(a, b):
    if not a or not b:
        return False
    for pinned, other in ((a, b), (b, a)):
        version = _exact(pinned)
        if version is not None:
            try:
                return not satisfies(version, other)
            except ValueError:
                return True
    return False


def disagreements(by_file):
    """Packages two requirements files cannot both be satisfied on.

    Only a real conflict counts: one file pins an exact version the other's
    specifier excludes. `==2.3.3` beside `<3.0` agrees, and a bare name beside
    a pin agrees too -- pip sees the pinned version installed and keeps it.
    """
    seen, out = {}, []
    for _path, reqs in by_file:
        for r in reqs:
            other = seen.get(r.key)
            if other and not (other.git or r.git) \
                    and _conflict(other.spec, r.spec):
                out.append((other, r))
            seen.setdefault(r.key, r)
    return out


def updated_line(finding):
    r = finding.req
    if r.git:
        url = r.git.group("url")
        body = f"{r.name}{r.extras} @ git+{url}@{finding.latest_text}"
    else:
        body = f"{r.name}{r.extras}=={finding.latest_text}"
    if r.marker:
        body += " " + r.marker.strip()
    if r.comment:
        body += "  " + r.comment.strip()
    indent = r.raw[:len(r.raw) - len(r.raw.lstrip())]
    return indent + body


def rewrite(path, findings):
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    for finding in findings:
        lines[finding.req.index] = updated_line(finding)
    ending = eol if text.endswith(("\n", "\r")) else ""
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(eol.join(lines) + ending)


def _annotate(level, req, title, message):
    """A GitHub Actions annotation, shown on the line in the PR's diff view."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    where = ""
    if req is not None:
        where = (f" file={os.path.basename(req.path)},"
                 f"line={req.index + 1},title={title}")
    say(f"::{level}{where}::{message}")


def _summary(behind, clashes, errors):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path or not (behind or clashes or errors):
        return
    rows = ["### Requirements", "",
            "| | file | package | pinned | latest |", "|---|---|---|---|---|"]
    for f in sorted(behind, key=lambda f: (f.req.path, f.req.key)):
        rows.append(f"| behind | {os.path.basename(f.req.path)} | "
                    f"{f.req.name} | `{f.problem}` | {f.latest_text} |")
    for a, b in clashes:
        rows.append(f"| **clash** | {os.path.basename(b.path)} | {a.name} | "
                    f"`{a.spec}` vs `{b.spec}` | |")
    rows += [f"| could not check | | {e} | | |" for e in errors]
    if behind:
        rows += ["", "Run `make requirements-update`, rebuild, run the tests "
                     "and commit the result."]
    with open(path, "a", encoding="utf-8") as out:
        out.write("\n".join(rows) + "\n")


def report(behind, clashes, errors):
    if behind:
        width = max(len(f.req.name) for f in behind)
        order = sorted(behind, key=lambda f: (f.req.path, f.req.key))
        for f in order:
            where = os.path.basename(f.req.path)
            say(f"  BEHIND  {where:22} {f.req.name:{width}}  "
                f"{f.problem:24} latest {f.latest_text}")
            _annotate("error", f.req, "Out of date",
                      f"{f.req.name} {f.problem}: latest is "
                      f"{f.latest_text}. make requirements-update")
    elif errors:
        say("  nothing behind among the requirements that could be checked")
    else:
        say("  every requirement admits its latest release")
    for a, b in clashes:
        say(f"  CLASH   {a.name}: {os.path.basename(a.path)} says "
            f"{a.spec!r}, {os.path.basename(b.path)} says {b.spec!r} -- "
            "the test image installs the second, so tests and production "
            "run different versions")
        _annotate("error", b, "Requirements clash",
                  f"{a.name} is {a.spec} in {os.path.basename(a.path)}: the "
                  "test image installs this file second, so tests and "
                  "production run different versions")
    for e in errors:
        say(f"  UNKNOWN {e}")
        _annotate("error", None, "", f"Could not check {e}")
    if errors:
        say("\nCould not check everything. That is not the same as up to "
            "date.")
    _summary(behind, clashes, errors)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--update", action="store_true",
                    help="rewrite out-of-date specifiers to the latest")
    ap.add_argument("--min-age-hours", type=float, default=MIN_AGE_HOURS,
                    help="hours a release must be public before it is "
                         "required (default: 48, or "
                         "$REQUIREMENTS_MIN_AGE_HOURS)")
    ap.add_argument("--python",
                    help="Python to resolve for, e.g. 3.11 "
                         "(default: from the Dockerfile)")
    args = ap.parse_args(argv)

    if args.python:
        python = tuple(int(p) for p in args.python.split("."))
    else:
        python = detect_python(args.root)
    paths = [os.path.join(args.root, n) for n in FILES]
    by_file = [(p, read_requirements(p)) for p in paths if os.path.exists(p)]
    if not by_file:
        say("check-requirements: no requirements files here")
        return 0

    reqs = [r for _, rs in by_file for r in rs]
    behind, errors = check(reqs, python, min_age_hours=args.min_age_hours)
    say(f"Checking {len(reqs)} requirements against the latest releases "
        f"for Python {fmt(python)} public for at least "
        f"{args.min_age_hours:g}h\n")

    if args.update and behind:
        for path, _ in by_file:
            mine = [f for f in behind if f.req.path == path]
            if mine:
                rewrite(path, mine)
        say(f"Updated {len(behind)} line(s). Rebuild and run the tests "
            "before committing.")
        by_file = [(p, read_requirements(p)) for p, _ in by_file]
        behind = []

    clashes = disagreements(by_file)
    report(behind, clashes, errors)
    if behind:
        say("\nOut of date. Run `make requirements-update`, rebuild, run "
            "the tests, and commit the result.")
    return 1 if (behind or clashes or errors) else 0


if __name__ == "__main__":
    sys.exit(main())
