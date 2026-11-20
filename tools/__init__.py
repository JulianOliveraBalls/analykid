"""Tools de AnalyKid: un módulo por tool y `common` con lo compartido."""
from tools.common import AnalyKidState, Context
from tools.enso import get_enso_status
from tools.knowledge import listar_skills, load_skill, search_knowledge_base
from tools.report import create_pdf
from tools.risk import evaluate_risk
from tools.river import get_river_discharge
from tools.weather import get_weather_forecast
from tools.web_search import web_search

# En el orden del flujo: datos, evaluación, conocimiento, informe.
TOOLS: list = [
    get_enso_status, get_weather_forecast, get_river_discharge, web_search,
    evaluate_risk, search_knowledge_base, load_skill, create_pdf,
]

__all__ = ["TOOLS", "AnalyKidState", "Context", "listar_skills"]
