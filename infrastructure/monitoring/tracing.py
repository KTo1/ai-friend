import time
import functools
import os
from typing import Dict, Any, Optional
import uuid
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from infrastructure.monitoring.logging import StructuredLogger


class TraceManager:
    """Менеджер трассировки для распределенного трейсинга"""

    def __init__(self):
        self.logger = StructuredLogger("tracing")
        self.propagator = TraceContextTextMapPropagator()
        self._tracing_setup = False

    def setup_tracing(self):
        """Настройка OpenTelemetry трассировки"""
        if self._tracing_setup:
            return

        enable_tracing = os.getenv("ENABLE_TRACING", "false").lower() == "true"
        if not enable_tracing:
            self.logger.info("Tracing disabled by configuration")
            return

        try:
            resource = Resource.create({
                "service.name": "friend-bot",
                "service.version": "1.0.0"
            })

            trace.set_tracer_provider(TracerProvider(resource=resource))

            jaeger_host = os.getenv("JAEGER_HOST", "localhost")
            jaeger_port = int(os.getenv("JAEGER_PORT", "6831"))

            jaeger_exporter = JaegerExporter(
                agent_host_name=jaeger_host,
                agent_port=jaeger_port,
            )

            trace.get_tracer_provider().add_span_processor(
                BatchSpanProcessor(jaeger_exporter)
            )

            self._tracing_setup = True
            self.logger.info(f"Tracing setup completed with Jaeger exporter ({jaeger_host}:{jaeger_port})")
        except Exception as e:
            self.logger.error(f"Failed to setup tracing: {e}")

    def get_tracer(self, name: str):
        if not self._tracing_setup:
            return trace.get_tracer(name)
        return trace.get_tracer(name)

    def create_trace_context(self) -> Dict[str, str]:
        carrier = {}
        self.propagator.inject(carrier)
        return carrier

    def extract_trace_context(self, carrier: Dict[str, str]) -> Any:
        return self.propagator.extract(carrier)


def trace_span(name: str, attributes: Dict[str, Any] = None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tracer_manager = TraceManager()
            tracer = tracer_manager.get_tracer(func.__module__)

            with tracer.start_as_current_span(name, attributes=attributes) as span:
                try:
                    if attributes:
                        for key, value in attributes.items():
                            span.set_attribute(key, value)

                    logger = StructuredLogger(func.__module__)
                    logger.info(f"Starting {name}", extra={'operation': name})

                    result = func(*args, **kwargs)

                    logger.info(f"Completed {name}", extra={'operation': name})

                    return result

                except Exception as e:
                    logger = StructuredLogger(func.__module__)
                    logger.error(f"Error in {name}: {str(e)}", extra={'operation': name})

                    span.record_exception(e)
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))

                    raise

        return wrapper

    return decorator


class SpanTimer:
    def __init__(self, span, operation: str):
        self.span = span
        self.operation = operation
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        self.span.set_attribute(f"{self.operation}.start_time", self.start_time)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.span.set_attribute(f"{self.operation}.duration", duration)
        self.span.set_attribute(f"{self.operation}.end_time", time.time())


trace_manager = TraceManager()