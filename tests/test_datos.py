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


def test_variables_por_defecto_existen() -> None:
    datos = _cargar("variables.json")
    assert set(datos["por_defecto"]) <= set(datos["variables"])


def test_variables_tienen_descripcion_y_unidades() -> None:
    for clave, v in _cargar("variables.json")["variables"].items():
        assert v["descripcion"], clave
        assert v["parametros"] and all(v["parametros"].values()), clave
