"""Uniform Prometheus metrics and OTLP tracing for an AIMS FastAPI service."""

import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator


def install_observability(app: FastAPI) -> None:
    """Expose RED metrics and export traces when an OTLP endpoint is configured."""
    Instrumentator(excluded_handlers=["/api/health/", "/healthz", "/metrics"]).instrument(app).expose(
        app, endpoint="/metrics", include_in_schema=False
    )

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return

    service_name = os.getenv("OTEL_SERVICE_NAME", os.getenv("AIMS_SERVICE_NAME", "aims-service"))
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=endpoint.startswith("http://")))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls="healthz,api/health,metrics")
