"""Print format rendering (Section 4.5).

Jinja2 templates live in backend/print_formats/ and are loaded once into an
Environment. WeasyPrint converts the rendered HTML to PDF; it is an optional
dependency (``pip install .[pdf]``) so environments without its native libs
can still run everything else — the endpoint then returns 501.

MANUAL_REVIEW: WeasyPrint assumed as PDF engine (vs. wkhtmltopdf).
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.exceptions import AppError, NotFoundError

PRINT_FORMATS_DIR = Path(__file__).resolve().parent.parent.parent / "print_formats"

_env = Environment(
    loader=FileSystemLoader(str(PRINT_FORMATS_DIR)),
    autoescape=select_autoescape(["html"]),
)


class PDFEngineUnavailable(AppError):
    status_code = 501
    code = "ERR_PDF_ENGINE_UNAVAILABLE"


def render_print_format(template_name: str, context: dict[str, Any]) -> str:
    """Render a print-format template to HTML."""
    if not (PRINT_FORMATS_DIR / template_name).exists():
        raise NotFoundError(f"Print format '{template_name}' not found")
    template = _env.get_template(template_name)
    return template.render(generated_on=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"), **context)


def html_to_pdf(html: str) -> bytes:
    try:
        from weasyprint import HTML  # noqa: PLC0415 — optional heavy import
    except ImportError as exc:
        raise PDFEngineUnavailable(
            "PDF generation requires WeasyPrint: pip install 'optireach-erp-backend[pdf]'"
        ) from exc
    return HTML(string=html).write_pdf()
