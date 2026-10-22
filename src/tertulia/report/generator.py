from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from .models import ReportData

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=True)


def render_html(data: ReportData) -> str:
    template = _env.get_template("report.html")
    return template.render(data=data)


def build_pdf(data: ReportData) -> bytes:
    from weasyprint import HTML  # lazy: requires GTK native libs
    html_source = render_html(data)
    return HTML(string=html_source).write_pdf()
