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
    assert r"\title{Plan \& riesgo 100\%}" in tex and "cuerpo" in tex
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
        {"amenaza": "Sanitaria", "nivel": "amarillo"}]}
    assert report.validar(_ejemplo(), riesgo) == []
