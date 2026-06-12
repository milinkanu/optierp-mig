"""Structured JSON logging via structlog with a per-request trace_id.

The trace_id is held in a contextvar so every log line emitted while handling
a request (including from services and background tasks started by it)
carries the same id (Section 9, rule 10).
"""

import contextvars
import logging
import sys
import uuid

import structlog

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")


def new_trace_id() -> str:
    tid = uuid.uuid4().hex[:16]
    trace_id_var.set(tid)
    return tid


def _add_trace_id(_logger: object, _method: str, event_dict: dict) -> dict:
    event_dict["trace_id"] = trace_id_var.get()
    return event_dict


def configure_logging(debug: bool = False) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.DEBUG if debug else logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_trace_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG if debug else logging.INFO),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
