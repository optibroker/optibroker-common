"""Keep credentials in URLs out of exported traces (OB-509, from OB-456).

The OpenTelemetry Operator auto-instruments every service. Its ``requests``
instrumentation records each outbound URL in full (``http.url`` / ``url.full``),
and a failed call's exception text embeds the URL too. Several providers take
their key in the query string (PropertyData ``key``, OpenWeather ``appid``,
TransportAPI ``app_id``/``app_key``), so the keys were being stored in Tempo,
readable by anyone with Grafana access. Upstream only redacts a fixed list of
AWS/Google signature parameters.

``RedactingSpanProcessor`` removes query strings and URL userinfo from a span
before it can be exported: its attributes, name, status description and event
attributes (an exception's message and stack trace). It cleans the span when it
starts and wraps the span's setters, so values written later are cleaned as they
arrive. Nothing reaches an exporter unredacted, whichever order the processors
run in.

This is defence in depth. The collector-side scrub (tracing-fleet #1) is still
the control for anything this process cannot see. Importing optibroker_common
installs the processor on the global tracer provider. Set
``OPTIBROKER_TRACE_REDACTION=off`` to disable it.
"""
import contextlib
import logging
import os
import re
import weakref
from urllib.parse import urlsplit, urlunsplit

try:
    from opentelemetry.sdk.trace import SpanProcessor
    from opentelemetry.trace import Status
except ImportError:  # tracing is not installed: nothing to redact
    SpanProcessor = object
    Status = None

logger = logging.getLogger(__name__)

REDACTED = "REDACTED"

# Attributes that hold a URL or a path with its query string.
URL_ATTRIBUTES = frozenset({"http.url", "url.full", "http.target"})
# Attributes that are nothing but a query string or a fragment.
QUERY_ATTRIBUTES = frozenset({"url.query", "url.fragment"})

# In free text (exception messages, stack traces, status descriptions): a "?"
# straight after a URL or path character, up to whitespace, a quote or a
# bracket. A "?" ending a sentence ("why?") is followed by a space and is left
# alone, and so is an SQL placeholder (" = ?").
_INLINE_QUERY = re.compile(r"(?<=[\w/.~%-])\?[^\s'\"<>()\[\]{}]+")
# user:password@ in a URL.
_INLINE_USERINFO = re.compile(r"(?<=://)[^/\s@'\"<>]+@")


def redact_text(value):
    """``value`` with any URL query string and userinfo replaced by REDACTED."""
    if not isinstance(value, str) or ("?" not in value and "@" not in value):
        return value
    value = _INLINE_USERINFO.sub(f"{REDACTED}@", value)
    return _INLINE_QUERY.sub(f"?{REDACTED}", value)


def redact_url(value):
    """A URL or path with its query, fragment and userinfo replaced by REDACTED."""
    if not isinstance(value, str):
        return value
    try:
        parts = urlsplit(value)
    except ValueError:
        return redact_text(value)
    netloc = parts.netloc
    if "@" in netloc:
        netloc = f"{REDACTED}@{netloc.rsplit('@', 1)[1]}"
    return urlunsplit((
        parts.scheme,
        netloc,
        parts.path,
        REDACTED if parts.query else "",
        REDACTED if parts.fragment else "",
    ))


def _redact_value(value):
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, (list, tuple)) and any(isinstance(v, str) for v in value):
        return type(value)(redact_text(v) for v in value)
    return value


def redact_attribute(key, value):
    """The value ``key`` may be exported with."""
    if key in QUERY_ATTRIBUTES:
        return REDACTED if value else value
    if key in URL_ATTRIBUTES:
        return redact_url(value)
    return _redact_value(value)


def redact_attributes(attributes):
    if not attributes:
        return attributes
    return {k: redact_attribute(k, v) for k, v in attributes.items()}


def _redact_status(status, description):
    if Status is not None and isinstance(status, Status) and status.description:
        status = Status(status.status_code, redact_text(status.description))
    return status, redact_text(description)


class RedactingSpanProcessor(SpanProcessor):
    """Cleans each span as it starts and wraps its setters, so nothing in it is
    exported with a URL query string or userinfo."""

    def on_start(self, span, parent_context=None):
        try:
            if not span.is_recording():
                return
            self._wrap_setters(span)
            for key, value in dict(span.attributes or {}).items():
                clean = redact_attribute(key, value)
                if clean != value:
                    span.set_attribute(key, clean)
            span.update_name(span.name)
        except Exception:  # never let redaction break the request it traces
            logger.exception("Trace redaction could not wrap a span")

    @staticmethod
    def _wrap_setters(span):
        set_attribute = span.set_attribute
        set_attributes = span.set_attributes
        add_event = span.add_event
        set_status = span.set_status
        update_name = span.update_name

        def _set_attribute(key, value):
            return set_attribute(key, redact_attribute(key, value))

        def _set_attributes(attributes):
            return set_attributes(redact_attributes(attributes))

        def _add_event(name, attributes=None, timestamp=None):
            return add_event(redact_text(name), redact_attributes(attributes), timestamp)

        def _set_status(status, description=None):
            return set_status(*_redact_status(status, description))

        def _update_name(name):
            return update_name(redact_text(name))

        # Instance attributes shadow the class's methods, so the span's own
        # record_exception (which calls self.add_event) is cleaned too.
        span.set_attribute = _set_attribute
        span.set_attributes = _set_attributes
        span.add_event = _add_event
        span.set_status = _set_status
        span.update_name = _update_name

    def on_end(self, span):
        pass

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        return True


_installed_on = weakref.WeakSet()


def install_trace_redaction(provider=None):
    """Add ``RedactingSpanProcessor`` to ``provider``, by default the global
    tracer provider. Returns True when redaction is in place.

    Does nothing when tracing is not installed, the provider is not the SDK's
    (no spans are exported), or ``OPTIBROKER_TRACE_REDACTION=off``. Installing
    twice on one provider adds it once.
    """
    if os.environ.get("OPTIBROKER_TRACE_REDACTION", "on").strip().lower() in ("off", "false", "0"):
        return False
    if SpanProcessor is object:
        return False
    if provider is None:
        from opentelemetry import trace
        provider = trace.get_tracer_provider()
    add = getattr(provider, "add_span_processor", None)
    if add is None:
        return False
    if provider in _installed_on:  # False for one that can't be weakly referenced
        return True
    add(RedactingSpanProcessor())
    with contextlib.suppress(TypeError):
        _installed_on.add(provider)
    return True
