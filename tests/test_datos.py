"""Tests de datos: forma de las allow-lists de datos/.

No pegan a la red: solo verifican que los JSON tengan lo que las tools van a leer.
"""
import json
from pathlib import Path

DATOS = Path(__file__).parent.parent / "datos"


def _cargar(nombre: str) -> dict:
    return json.loads((DATOS / nombre).read_text(encoding="utf-8"))


def test_localidades_dentro_de_mendoza() -> None:
    localidades = _cargar("localidades.json")["localidades"]
    assert len(localidades) >= 18
    for clave, l in localidades.items():
        # Caja aproximada de la provincia: si falla, la coordenada está mal cargada.
        assert -37.6 < l["latitud"] < -32.0, clave
        assert -70.6 < l["longitud"] < -66.5, clave
        assert l["nombre"] and l["departamento"] and l["oasis"], clave


def test_localidades_claves_snake_case() -> None:
    for clave in _cargar("localidades.json")["localidades"]:
        assert clave == clave.lower() and " " not in clave and clave.isascii(), clave


def test_variables_tienen_descripcion_y_unidades() -> None:
    for clave, v in _cargar("variables.json")["variables"].items():
        assert v["descripcion"], clave
        assert v["parametros"] and all(v["parametros"].values()), clave


def test_localidades_tienen_rio_piedemonte_y_emergencias() -> None:
    rios = set(_cargar("rios.json")["rios"])
    for clave, l in _cargar("localidades.json")["localidades"].items():
        assert l["rio"] in rios, clave
        assert isinstance(l["piedemonte"], bool), clave
        assert l["emergencias"]["general"] == "911", clave


def test_rios_tienen_punto_de_consulta() -> None:
    for clave, r in _cargar("rios.json")["rios"].items():
        assert -37.6 < r["consulta"]["latitud"] < -32.0, clave
        assert -70.6 < r["consulta"]["longitud"] < -66.5, clave


def test_dominios_oficiales() -> None:
    datos = _cargar("dominios_oficiales.json")
    assert datos["dominios"] and all(d["dominio"] and d["organismo"] for d in datos["dominios"])
    assert datos["antiguedad_maxima_horas"] > 0 and datos["max_resultados"] > 0
    assert "{zona}" in datos["plantilla_consulta"]
