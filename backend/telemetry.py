"""
OpenTelemetry configuration for Aviation Multi-Agent Solver.
Configures TracerProvider, FastAPIInstrumentor, Azure Monitor + OTLP exporters.
Includes structlog integration for trace/span correlation.
"""

import os
import structlog

logger = structlog.get_logger()

# Service metadata
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "aviation-multi-agent")
SERVICE_VERSION = "1.0.0"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")


def configure_telemetry(app=None):
    """
    Configure OpenTelemetry with Azure Monitor and OTLP exporters.

    Args:
        app: FastAPI app instance for instrumentation
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({
            "service.name": SERVICE_NAME,
            "service.version": SERVICE_VERSION,
            "deployment.environment": ENVIRONMENT,
            "service.namespace": "aviation-multi-agent",
        })

        provider = TracerProvider(resource=resource)

        # Add OTLP exporter if endpoint configured
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        if otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info("otel_otlp_configured", endpoint=otlp_endpoint)

        # Add Azure Monitor exporter if connection string configured
        app_insights_conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
        if app_insights_conn:
            from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            azure_exporter = AzureMonitorTraceExporter(
                connection_string=app_insights_conn,
            )
            provider.add_span_processor(BatchSpanProcessor(azure_exporter))
            logger.info("otel_azure_monitor_configured")

        trace.set_tracer_provider(provider)

        # Instrument FastAPI if app provided
        if app:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(app)
            logger.info("otel_fastapi_instrumented")

        logger.info(
            "otel_configured",
            service=SERVICE_NAME,
            environment=ENVIRONMENT,
        )

    except ImportError as e:
        logger.warning("otel_not_available", error=str(e))
    except Exception as e:
        logger.error("otel_configuration_failed", error=str(e))


def get_tracer(name: str = SERVICE_NAME):
    """Get a tracer instance."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return None


def traced_span(tracer, span_name: str):
    """
    Create a traced span context manager.
    Returns a no-op context manager if tracer is None.
    """
    if tracer is None:
        import contextlib
        return contextlib.nullcontext()
    return tracer.start_as_current_span(span_name)


def get_current_trace_context() -> dict | None:
    """
    Return the current OTel trace context as hex IDs.

    Shape:
      {"trace_id": "...", "span_id": "...", "parent_span_id": "...|None"}
    """
    try:
        from opentelemetry import trace as otel_trace

        span = otel_trace.get_current_span()
        if span is None:
            return None

        span_ctx = span.get_span_context()
        if span_ctx is None or not span_ctx.is_valid:
            return None

        parent_span_id = None
        parent = getattr(span, "parent", None)
        if parent is not None and getattr(parent, "is_valid", False):
            parent_span_id = f"{parent.span_id:016x}"

        return {
            "trace_id": f"{span_ctx.trace_id:032x}",
            "span_id": f"{span_ctx.span_id:016x}",
            "parent_span_id": parent_span_id,
        }
    except ImportError:
        return None
    except Exception as e:
        logger.warning("otel_context_lookup_failed", error=str(e))
        return None
