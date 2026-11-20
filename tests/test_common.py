"""Tests de tools/common.py: pedir() ante 429, 5xx, timeout y errores definitivos (sin red)."""
import requests

from tools import common
from tools.common import pedir


class _Resp:
    def __init__(self, status: int, cuerpo=None):
        self.status_code, self._cuerpo = status, cuerpo

    def json(self):
        if self._cuerpo is None:
            raise ValueError
        return self._cuerpo

    @property
    def text(self):
        return "texto plano"


def _simular(monkeypatch, respuestas: list):
    """Reemplaza requests.get por una secuencia de respuestas (o excepciones)."""
    llamadas = []

    def get(url, params, timeout):
        llamadas.append(timeout)
        r = respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(common.requests, "get", get)
    return llamadas


def test_ok_al_primer_intento(monkeypatch):
    llamadas = _simular(monkeypatch, [_Resp(200, {"a": 1})])
    assert pedir("u", {}, esperar=lambda s: None) == ({"a": 1}, None)
    assert llamadas == [common.TIMEOUT_S]


def test_429_reintenta_con_esperas_crecientes(monkeypatch):
    _simular(monkeypatch, [_Resp(429), _Resp(503), _Resp(200, {"ok": True})])
    esperas = []
    assert pedir("u", {}, esperar=esperas.append) == ({"ok": True}, None)
    assert esperas == [2, 4]


def test_timeout_agota_los_intentos(monkeypatch):
    _simular(monkeypatch, [requests.Timeout()] * 4)
    esperas = []
    datos, causa = pedir("u", {}, esperar=esperas.append)
    assert datos is None and "no respondió" in causa and "4 intentos" in causa
    assert esperas == [2, 4, 8]


def test_404_no_reintenta(monkeypatch):
    llamadas = _simular(monkeypatch, [_Resp(404)])
    datos, causa = pedir("u", {}, esperar=lambda s: None)
    assert datos is None and "HTTP 404" in causa and len(llamadas) == 1


def test_respuesta_no_json_devuelve_texto(monkeypatch):
    _simular(monkeypatch, [_Resp(200)])
    assert pedir("u", {}, esperar=lambda s: None) == ("texto plano", None)


def test_error_de_conexion_se_reintenta(monkeypatch):
    _simular(monkeypatch, [requests.ConnectionError(), _Resp(200, [1])])
    assert pedir("u", {}, esperar=lambda s: None) == ([1], None)
