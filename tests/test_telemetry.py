"""Exported traces carry no URL query strings or userinfo (OB-509, from OB-456).

The OpenTelemetry Operator auto-instruments every service. Its requests
instrumentation passes the URL attributes in when it creates a client span, and
a failed call's exception is recorded on the span as it leaves. The SDK-only
tests below do exactly that. The tests marked "real instrumentation" also run
opentelemetry-instrumentation-requests itself, against a local server and a
closed port, where it is installed. It is not in requirements_test.txt because
it only has beta releases, which check-requirements cannot vouch for.
"""
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytest.importorskip("opentelemetry.sdk")

import requests  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402
from opentelemetry.trace import ProxyTracerProvider, SpanKind, Status, StatusCode  # noqa: E402

from optibroker_common import telemetry  # noqa: E402
from optibroker_common.telemetry import (  # noqa: E402
    REDACTED, RedactingSpanProcessor, install_trace_redaction, redact_attribute, redact_text, redact_url,
)

KEY = "pk_live_5ecret"


class _Ok(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def server():
    httpd = HTTPServer(("127.0.0.1", 0), _Ok)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def _provider():
    """A provider whose exporter is registered BEFORE the redactor: the order in
    which a redactor that ran only when a span ends would be too late."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    assert install_trace_redaction(provider) is True
    return provider, exporter


@pytest.fixture
def traced():
    """The real requests instrumentation, exporting to memory."""
    instrumentation = pytest.importorskip("opentelemetry.instrumentation.requests")
    provider, exporter = _provider()
    instrumentation.RequestsInstrumentor().instrument(tracer_provider=provider)
    yield exporter
    instrumentation.RequestsInstrumentor().uninstrument()


def _exported_text(exporter):
    spans = exporter.get_finished_spans()
    assert spans, "no span was exported"
    return "\n".join(span.to_json() for span in spans)


def test_client_span_created_with_a_keyed_url_exports_none_of_it():
    provider, exporter = _provider()
    url = f"https://api.example/data/2.5/air_pollution?appid={KEY}"
    tracer = provider.get_tracer("requests-like")

    with pytest.raises(requests.ConnectionError), tracer.start_as_current_span(
            "GET", kind=SpanKind.CLIENT,
            attributes={"http.url": url, "url.full": url, "url.query": f"appid={KEY}"}):
        raise requests.ConnectionError(
            f"HTTPSConnectionPool(host='api.example', port=443): Max retries exceeded with url: "
            f"/data/2.5/air_pollution?appid={KEY} (Caused by NewConnectionError)")

    assert KEY not in _exported_text(exporter)
    (span,) = exporter.get_finished_spans()
    assert span.attributes["http.url"] == f"https://api.example/data/2.5/air_pollution?{REDACTED}"
    assert any(e.name == "exception" for e in span.events)
    assert span.status.status_code is StatusCode.ERROR


def test_outbound_call_url_keeps_no_query(traced, server):
    requests.get(f"{server}/api/property?key={KEY}&postcode=AB1+2CD", timeout=5)

    (span,) = traced.get_finished_spans()
    assert span.attributes["http.url"] == f"{server}/api/property?{REDACTED}"
    exported = _exported_text(traced)
    assert KEY not in exported
    assert "AB1" not in exported  # personal data in queries goes too (OB-418)


def test_failed_call_exception_text_keeps_no_query(traced):
    with pytest.raises(requests.ConnectionError) as raised:
        requests.get(f"http://127.0.0.1:1/data/2.5/air_pollution?appid={KEY}", timeout=2)
    assert KEY in str(raised.value)  # requests does put the key in the message

    exported = _exported_text(traced)
    assert KEY not in exported
    (span,) = traced.get_finished_spans()
    event = next(e for e in span.events if e.name == "exception")
    assert KEY not in event.attributes["exception.message"]
    assert KEY not in event.attributes["exception.stacktrace"]
    assert span.status.status_code is StatusCode.ERROR
    assert KEY not in (span.status.description or "")


def test_userinfo_is_redacted(traced, server):
    host = server.split("//")[1]
    requests.get(f"http://user:{KEY}@{host}/x", timeout=5)
    assert KEY not in _exported_text(traced)


def test_values_set_after_start_are_redacted():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    provider.add_span_processor(RedactingSpanProcessor())
    tracer = provider.get_tracer("t")

    with tracer.start_as_current_span(f"GET /a?key={KEY}") as span:
        span.set_attribute("url.full", f"https://h/a?key={KEY}")
        span.set_attributes({"http.target": f"/a?app_key={KEY}", "url.query": f"key={KEY}"})
        span.add_event("retry", {"detail": f"calling https://h/a?key={KEY}"})
        span.set_status(Status(StatusCode.ERROR, f"failed https://h/a?key={KEY}"))
        span.update_name(f"GET /b?key={KEY}")

    (done,) = exporter.get_finished_spans()
    assert KEY not in done.to_json()
    assert done.attributes["url.full"] == f"https://h/a?{REDACTED}"
    assert done.attributes["http.target"] == f"/a?{REDACTED}"
    assert done.attributes["url.query"] == REDACTED


@pytest.mark.parametrize("value, expected", [
    ("https://h/p?key=1&b=2", f"https://h/p?{REDACTED}"),
    ("https://h/p", "https://h/p"),
    ("/p?x=1", f"/p?{REDACTED}"),
    ("https://u:pw@h/p", f"https://{REDACTED}@h/p"),
    ("https://h/p#access_token=1", f"https://h/p#{REDACTED}"),
])
def test_redact_url(value, expected):
    assert redact_url(value) == expected


@pytest.mark.parametrize("text, expected", [
    ("Max retries exceeded with url: /api?key=1 (Caused by X)",
     f"Max retries exceeded with url: /api?{REDACTED} (Caused by X)"),
    ("HTTPError: 403 for url: https://h/p?appid=1", f"HTTPError: 403 for url: https://h/p?{REDACTED}"),
    ("is this a question? yes", "is this a question? yes"),
    ("SELECT * FROM t WHERE id = ?", "SELECT * FROM t WHERE id = ?"),
    ("'https://a:b@h/p'", f"'https://{REDACTED}@h/p'"),
])
def test_redact_text(text, expected):
    assert redact_text(text) == expected


def test_non_url_attributes_are_untouched():
    assert redact_attribute("http.status_code", 200) == 200
    assert redact_attribute("http.route", "/client/<id>") == "/client/<id>"
    assert redact_attribute("url.query", "") == ""


def test_install_once_per_provider():
    provider = TracerProvider()
    assert install_trace_redaction(provider) is True
    assert install_trace_redaction(provider) is True
    processors = provider._active_span_processor._span_processors  # noqa: SLF001
    assert sum(isinstance(p, RedactingSpanProcessor) for p in processors) == 1


def test_no_sdk_provider_means_nothing_to_install():
    assert install_trace_redaction(ProxyTracerProvider()) is False


def test_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("OPTIBROKER_TRACE_REDACTION", "off")
    assert install_trace_redaction(TracerProvider()) is False


def test_without_tracing_installed_nothing_happens(monkeypatch):
    monkeypatch.setattr(telemetry, "SpanProcessor", object)
    assert install_trace_redaction(TracerProvider()) is False


def test_importing_the_package_installs_it_on_the_global_provider():
    # As the Operator's auto-instrumentation does: the SDK provider is global
    # before any application code (and so optibroker_common) is imported.
    code = (
        "import json\n"
        "from opentelemetry import trace\n"
        "from opentelemetry.sdk.trace import TracerProvider\n"
        "trace.set_tracer_provider(TracerProvider())\n"
        "import optibroker_common\n"
        "from optibroker_common.telemetry import RedactingSpanProcessor\n"
        "ps = trace.get_tracer_provider()._active_span_processor._span_processors\n"
        "print(json.dumps(sum(isinstance(p, RedactingSpanProcessor) for p in ps)))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == 1
