#!/usr/bin/env python3
"""Fail if any requirement is held below its latest release.

Run by `make requirements-check` on every pull request. A requirement is out
of date when its specifier does not admit the newest release on PyPI that
supports the repo's Python. That covers `==` pins that have fallen behind and
upper bounds such as `Werkzeug<3.0`; unpinned and `>=` lines always admit the
latest, so they pass. `pkg @ git+...@vX` is compared with the newest tag.

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


def pypi_latest(name, python):
    """Newest non-yanked final release with a file that installs here."""
    data = _get_json(PYPI.format(name=name))
    if data is None:
        raise LookupError(f"PyPI has no project named {name!r}")
    best = None
    for text, files in data.get("releases", {}).items():
        parsed = parse_version(text)
        if not parsed or parsed[1]:
            continue
        live = [f for f in files if not f.get("yanked")]
        if not any(_python_ok(f.get("requires_python"), python)
                   for f in live):
            continue
        if best is None or _cmp(parsed[0], best[0]) > 0:
            best = (parsed[0], text)
    if best is None:
        raise LookupError(
            f"no release of {name} supports Python {fmt(python)}")
    return best


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
    return best


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


def _lookup(key, python):
    kind, ident = key
    try:
        if kind == "git":
            return key, git_latest(ident), None
        return key, pypi_latest(ident, python), None
    except Exception as e:   # reported, never treated as up to date
        return key, None, f"{ident}: {e}"


def _source(req):
    return ("git", req.git.group("url")) if req.git else ("pypi", req.key)


def _behind(req, latest):
    if req.git:
        ref = req.git.group("ref") or ""
        current = parse_version(ref)
        if not current or _cmp(current[0], latest[0]) < 0:
            problem = f"at {ref or 'default branch'}"
            return Finding(req, latest[0], latest[1], problem)
        return None
    if req.spec and not satisfies(latest[0], req.spec):
        return Finding(req, latest[0], latest[1], req.spec)
    return None


def check(reqs, python, workers=16):
    """-> (behind, errors); `errors` lists what could not be checked."""
    keys = list(dict.fromkeys(_source(r) for r in reqs))
    latest, errors = {}, []
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        for key, value, err in pool.map(lambda k: _lookup(k, python), keys):
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


def report(behind, clashes, errors):
    if behind:
        width = max(len(f.req.name) for f in behind)
        order = sorted(behind, key=lambda f: (f.req.path, f.req.key))
        for f in order:
            where = os.path.basename(f.req.path)
            say(f"  BEHIND  {where:22} {f.req.name:{width}}  "
                f"{f.problem:24} latest {f.latest_text}")
    else:
        say("  every requirement admits its latest release")
    for a, b in clashes:
        say(f"  CLASH   {a.name}: {os.path.basename(a.path)} says "
            f"{a.spec!r}, {os.path.basename(b.path)} says {b.spec!r} -- "
            "the test image installs the second, so tests and production "
            "run different versions")
    for e in errors:
        say(f"  UNKNOWN {e}")
    if errors:
        say("\nCould not check everything. That is not the same as up to "
            "date.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--update", action="store_true",
                    help="rewrite out-of-date specifiers to the latest")
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
    behind, errors = check(reqs, python)
    say(f"Checking {len(reqs)} requirements against the latest releases "
        f"for Python {fmt(python)}\n")

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
