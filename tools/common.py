"""Piezas compartidas por todas las tools: estado, contexto, respuesta y HTTP.

Regla de todas las tools: nunca lanzan excepciones. Ante una falla devuelven
un texto que empieza con `ERROR <tool>:` y dice qué puede hacer el agente.
"""
import json
import time
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Annotated, Any

import requests
from langchain.agents import AgentState
from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime
from langgraph.types import Command

BASE_DIR = Path(__file__).resolve().parent.parent
DATOS_DIR = BASE_DIR / "datos"

TIMEOUT_S = 20
ESPERAS_S = (2, 4, 8)                 # entre intentos ante 429, 5xx o timeout
REINTENTABLES = {429, 500, 502, 503, 504}


@dataclass
class Context:
    """Datos de solo lectura de cada invocación (runtime context, no se guarda en el estado)."""
    turn: int


def _merge_sources(actuales: list | None, nuevas: list) -> list:
    """Reducer: acumula fuentes sin repetir la misma URL dentro de un turno."""
    por_clave = {(s["turn"], s["url"]): s for s in (actuales or []) + nuevas}
    return list(por_clave.values())


class AnalyKidState(AgentState):
    """Estado del agente: `messages` (heredado) + fuentes consultadas por turno."""
    sources: Annotated[list[dict], _merge_sources]


def respond(runtime: ToolRuntime[Any, Any], texto: str, artifact=None, **update) -> Command:
    """Doble canal: `texto` breve va al modelo; `artifact` (datos completos) solo a la UI.

    Además actualiza el estado con `update` (por ejemplo, `sources=`).
    """
    msg = ToolMessage(texto, tool_call_id=runtime.tool_call_id, artifact=artifact)
    return Command(update={**update, "messages": [msg]})


def error(tool: str, causa: str, sugerencia: str) -> str:
    """Formato único de error que el modelo puede leer y usar."""
    return f"ERROR {tool}: {causa}. {sugerencia}"


def pedir(url: str, params: dict, *, esperar=time.sleep) -> tuple[Any, str | None]:
    """GET con timeout y reintentos. Devuelve `(datos, None)` o `(None, causa)`.

    Reintenta ante 429, 5xx, timeout o falla de conexión, esperando 2, 4 y 8 s.
    `datos` es el JSON de la respuesta, o el texto si no es JSON.
    """
    causa = "sin respuesta"
    for espera in (*ESPERAS_S, None):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT_S)
        except requests.Timeout:
            causa = f"la fuente no respondió en {TIMEOUT_S} s"
        except requests.RequestException as e:
            causa = f"no se pudo conectar ({type(e).__name__})"
        else:
            if r.status_code == 200:
                try:
                    return r.json(), None
                except ValueError:
                    return r.text, None
            causa = f"la fuente respondió HTTP {r.status_code}"
            if r.status_code not in REINTENTABLES:
                return None, causa
        if espera is not None:
            esperar(espera)
    return None, causa + " después de 4 intentos"


@cache
def cargar_json(nombre: str) -> dict:
    """Lee un archivo de datos/ (allow-lists y catálogos), una sola vez por proceso."""
    return json.loads((DATOS_DIR / nombre).read_text(encoding="utf-8"))
