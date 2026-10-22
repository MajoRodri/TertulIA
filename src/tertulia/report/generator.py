from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from .models import ReportData

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=True)


def render_html(data: ReportData) -> str:
    template = _env.get_template("report.html")
    return template.render(data=data)


def build_pdf(data: ReportData) -> bytes:
    html_source = render_html(data)
    return HTML(string=html_source).write_pdf()
