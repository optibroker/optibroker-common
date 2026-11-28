__version__ = "1.5.0"


def _install_trace_redaction():
    # Every service imports this package, so the span processor that keeps
    # credentials in URLs out of exported traces is installed without any
    # service code (OB-509). Importing the package must never fail because of it.
    try:
        from optibroker_common.telemetry import install_trace_redaction
        install_trace_redaction()
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("Trace redaction was not installed")


_install_trace_redaction()
