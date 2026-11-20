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


def pedir(url: str, params: dict | None = None, *, cuerpo: dict | None = None,
          headers: dict | None = None, esperar=time.sleep) -> tuple[Any, str | None]:
    """HTTP con timeout y reintentos. Devuelve `(datos, None)` o `(None, causa)`.

    GET con `params`, o POST con `cuerpo` JSON. Reintenta ante 429, 5xx, timeout
    o falla de conexión, esperando 2, 4 y 8 s. `datos` es el JSON de la
    respuesta, o el texto si no es JSON.
    """
    metodo = "POST" if cuerpo is not None else "GET"
    causa = "sin respuesta"
    for espera in (*ESPERAS_S, None):
        try:
            r = requests.request(metodo, url, params=params, json=cuerpo,
                                 headers=headers, timeout=TIMEOUT_S)
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


def resultados_del_turno(mensajes: list) -> dict[str, Any]:
    """Último artifact válido de cada tool desde el último mensaje del usuario.

    Lo usan las tools que trabajan sobre lo que otras ya devolvieron (evaluate_risk,
    create_pdf): leen el estado en lugar de pedirle al modelo que copie los datos.
    Un resultado que empieza con ERROR no cuenta.
    """
    inicio = max((i for i, m in enumerate(mensajes) if m.type == "human"), default=-1)
    nombres, resultados = {}, {}
    for m in mensajes[inicio + 1:]:
        if m.type == "ai":
            nombres.update({c["id"]: c["name"] for c in m.tool_calls})
        elif m.type == "tool" and m.tool_call_id in nombres:
            if m.artifact is not None and not str(m.content).startswith("ERROR"):
                resultados[nombres[m.tool_call_id]] = m.artifact
    return resultados
