"""Tests de create_pdf: plantilla, rechazo de comandos y compilación del ejemplo de la skill."""
import re
from pathlib import Path

import pytest

from tools import report

SKILL = Path(__file__).parent.parent / "skills" / "informe_riesgo.md"


def _ejemplo() -> str:
    return re.search(r"```latex\n(.*?)```", SKILL.read_text(encoding="utf-8"), re.S).group(1)


def test_plantilla_tiene_macros_y_descargo():
    tex = report.armar_tex("Plan & riesgo 100%", "cuerpo")
    assert r"\LARGE\bfseries Plan \& riesgo 100\%}" in tex and "cuerpo" in tex
    assert all(rf"\newcommand{{\nivel{n}}}" in tex for n in ("verde", "amarillo", "naranja", "rojo", "sindatos"))
    assert "no reemplaza las alertas oficiales del SMN" in tex


def test_ejemplo_de_la_skill_no_usa_comandos_prohibidos():
    assert not any(p in _ejemplo() for p in report.PROHIBIDO)


@pytest.mark.skipif(report._tectonic() is None, reason="Tectonic no está instalado")
def test_ejemplo_de_la_skill_compila(tmp_path):
    tex = tmp_path / "ejemplo.tex"
    tex.write_text(report.armar_tex("Plan de contingencia", _ejemplo()), encoding="utf-8")
    proc = report.compilar(report._tectonic(), tex)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert tex.with_suffix(".pdf").exists()


def test_ejemplo_de_la_skill_pasa_el_control_de_contenido():
    riesgo = {"etapa": {"etapa": "floración"}, "amenazas": [
        {"amenaza": "Pluvial", "nivel": "amarillo"}, {"amenaza": "Granizo / tormenta", "nivel": "verde"},
        {"amenaza": "Aluvional", "nivel": "verde"}, {"amenaza": "Crecida", "nivel": "verde"},
        {"amenaza": "Sanitaria", "nivel": "amarillo"}],
        "ventanas": {"Sanitaria": {"antes": "20/11 al 23/11", "durante": "24/11", "despues": "29/11 al 04/12"},
                     "Pluvial": {"antes": "20/11 al 23/11", "durante": "24/11", "despues": "25/11 al 27/11"}}}
    assert report.validar(_ejemplo(), riesgo) == []


def test_etiqueta_acepta_la_fecha_sin_hoy():
    riesgo = {"amenazas": [], "ventanas": {"Pluvial": {"antes": "hoy, 20/11", "durante": "21/11",
                                                       "despues": "22/11 al 24/11"}}}
    con_hoy = "\\section{Medidas por amenaza}\n\\subsection{Pluvial}\n\\textbf{Antes (hoy, 20/11):}"
    sin_hoy = con_hoy.replace("hoy, ", "")
    otra = con_hoy.replace("hoy, 20/11", "19/11")
    falta = "falta «Antes (hoy, 20/11)»"
    assert not any(falta in p for p in report.validar(con_hoy, riesgo))
    assert not any(falta in p for p in report.validar(sin_hoy, riesgo))
    assert any(falta in p for p in report.validar(otra, riesgo))


def test_las_skills_no_superan_el_limite_de_load_skill():
    from tools.knowledge import MAX_SKILL, SKILLS_DIR
    for skill in SKILLS_DIR.glob("*.md"):
        assert len(skill.read_text(encoding="utf-8")) <= MAX_SKILL, skill.name


def test_escapar_ampersands_fuera_de_tablas():
    cuerpo = (r"\section{Fuentes} Corpus (Texas A&M, AWRI)." "\n"
              r"\begin{tabular}{ll} A & B \\ \end{tabular}" "\n"
              r"Ya escapado: A\&M. \url{https://x.org/?a=1&b=2}")
    salida = report.escapar_ampersands(cuerpo)
    assert r"Texas A\&M" in salida
    assert "A & B" in salida
    assert r"A\&M." in salida and r"\\&" not in salida
    assert "a=1&b=2" in salida


def test_escapar_porcentajes_sueltos_y_no_en_urls():
    cuerpo = (r"Probabilidad del 35 % y del 73\%. \url{https://x.org/a%20b}" "\n"
              r"Prob. (\%) & 35 % \\")
    salida = report.escapar_porcentajes(cuerpo)
    assert r"del 35 \% y del 73\%." in salida
    assert r"\url{https://x.org/a%20b}" in salida
    assert r"Prob. (\%) & 35 \% \\" in salida


def test_escapar_ampersands_despues_de_longtable():
    cuerpo = r"\begin{longtable}{ll} x & y \\ \end{longtable} P&G"
    assert report.escapar_ampersands(cuerpo) == r"\begin{longtable}{ll} x & y \\ \end{longtable} P\&G"


def _muestra() -> dict:
    return {
        "get_weather_forecast": {
            "nombre": "Tupungato", "oasis": "Valle de Uco", "rio": "tunuyan", "piedemonte": True,
            "dias": [{"fecha": "2026-11-26", "lluvia_mm": 1.6, "prob_pct": 73, "cape_jkg": 1050, "rafaga_kmh": 36,
                      "tmax_c": 23.7, "tmin_c": 13.0},
                     {"fecha": "2026-11-27", "lluvia_mm": 27.4, "prob_pct": 85, "cape_jkg": 550, "rafaga_kmh": 35,
                      "tmax_c": 20.1, "tmin_c": 13.4}],
            "indicadores": {"lluvia_acumulada_mm": 29.0, "lluvia_max_mm": 27.4, "fecha_lluvia_max": "2026-11-27",
                            "cape_max_jkg": 1050, "fecha_cape_max": "2026-11-26", "rafaga_max_kmh": 36,
                            "fecha_rafaga_max": "2026-11-26", "tmin_mas_baja_c": 13.0,
                            "fecha_tmin_mas_baja": "2026-11-26", "dias_favorables_hongos": 1},
            "emergencias": {"general": "911", "defensa_civil_municipal": "2622 574912", "verificado": "2026-11-20"},
        },
        "get_river_discharge": {"nombre": "Río Tunuyán", "caudal_max_m3s": 19.0, "fecha_max": "2026-11-27",
                                "media_1991_2020_m3s": 22.0, "cociente": 0.86, "tendencia": "estable",
                                "serie": [{"fecha": "2026-11-26", "caudal_m3s": 19.0, "media_1991_2020_m3s": 22.0},
                                          {"fecha": "2026-11-27", "caudal_m3s": 18.5, "media_1991_2020_m3s": 22.1}]},
        "web_search": {"elegidos": [{"titulo": "Alerta por tormentas 100% & granizo_#1", "dominio": "smn.gob.ar",
                                     "es_alerta": True}]},
        "evaluate_risk": {"nivel_maximo": "naranja", "etapa": {"etapa": "cuaje", "periodo_critico": True},
                          "amenazas": [{"amenaza": "Pluvial", "nivel": "naranja", "motivo": "Lluvia máx. 27.4 mm"},
                                       {"amenaza": "Crecida", "nivel": "verde", "motivo": "Caudal 0.86 veces la media"}],
                          "ventanas": {"Pluvial": {"antes": "26/11", "durante": "27/11", "despues": "28/11 al 30/11"}}},
    }


def test_panel_escapa_el_texto_externo_y_no_usa_comandos_prohibidos():
    from tools.panel import panel_latex
    panel = panel_latex(_muestra())
    assert r"100\% \& granizo\_\#1" in panel
    assert not any(p in panel for p in report.PROHIBIDO)
    assert "Tupungato" in panel and "Río Tunuyán" in panel and "NARANJA" in panel


def test_panel_vacio_sin_datos():
    from tools.panel import panel_latex
    assert panel_latex({}) == ""


def test_panel_compila_con_el_ejemplo_de_la_skill(tmp_path):
    from tools.panel import panel_latex
    tectonic = report._tectonic()
    if not tectonic:
        pytest.skip("Tectonic no está instalado")
    tex = tmp_path / "plan.tex"
    tex.write_text(report.armar_tex("Plan de contingencia", _ejemplo(), panel_latex(_muestra())), encoding="utf-8")
    proc = report.compilar(tectonic, tex)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert tex.with_suffix(".pdf").exists()
