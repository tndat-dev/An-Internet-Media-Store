"""Uniform Prometheus metrics and OTLP tracing for an AIMS FastAPI service."""

import os
from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator


def install_observability(app: FastAPI) -> None:
    Instrumentator(excluded_handlers=["/api/health/", "/healthz", "/metrics"]).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return
    resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", os.getenv("AIMS_SERVICE_NAME", "aims-service"))})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=endpoint.startswith("http://"))))
    meter_provider = MeterProvider(resource=resource, metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint, insecure=endpoint.startswith("http://")), export_interval_millis=15000)])
    trace.set_tracer_provider(provider)
    metrics.set_meter_provider(meter_provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, meter_provider=meter_provider, excluded_urls="healthz,api/health,metrics")
