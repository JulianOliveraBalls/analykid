"""Agente: lógica del agente con streaming; la interfaz es app.py (Streamlit).

`stream_turn` ejecuta un turno y emite *eventos* (razonamiento, llamadas a tools,
resultados, texto) a medida que el agente avanza. `saved_turns` reconstruye los
mismos eventos desde la conversación guardada. Cada interfaz solo los presenta.

Ejecutar:  streamlit run app.py
"""
import os
import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from uuid import uuid4

from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver

from model import get_fallback, get_model
from tools import TOOLS, Context, AnalyKidState, listar_skills
from middleware import continuar_si_solo_anuncia
from tools.common import es_recordatorio

# La fecha se fija al iniciar el programa; no se actualiza si la sesión cruza la medianoche.
HOY = date.today()
MODELO = f"{os.getenv('MODEL_PROVIDER', 'google_genai')} · {os.getenv('MODEL_NAME', 'gemini-3.5-flash-lite')}"
if os.getenv("MODEL_FALLBACK"):
    MODELO += f" (respaldo: {os.getenv('MODEL_FALLBACK')})"

SYSTEM_PROMPT = f"""Sos AnalyKid: armás planes de contingencia en PDF ante el riesgo hídrico y \
climático de fincas y localidades de Mendoza durante El Niño 2026-2027. Respondé en español \
rioplatense, claro y conciso. Hoy es {HOY.strftime("%d/%m/%Y")}; no asumas otro año.

# Datos de la tarea
Necesitás localidad (del catálogo de Mendoza), perfil (vid, frutal, hortaliza o urbano), \
superficie si es una finca, y cantidad de días (7 si no la dicen). Si falta la localidad o el \
perfil, preguntá una sola vez, todo junto. Fuera de alcance: coordenadas libres, Zonda, heladas \
y nieve; si lo piden, decilo y seguí con lo que sí cubrís.

# Flujo (5 pasos)
Antes de cada grupo de tools, explicá en 1-2 líneas qué vas a consultar y por qué. Pedí en \
paralelo todas las tools de un mismo paso, en una sola respuesta.
1. Datos: get_weather_forecast, get_river_discharge y web_search con la misma localidad. Solo \
la primera vez en la conversación, sumá get_enso_status y load_skill("fuentes_datos").
2. evaluate_risk con el perfil: calcula el semáforo, la etapa del cultivo, los días críticos, \
el escalamiento y qué buscar en el corpus. No evalúes los niveles por tu cuenta.
3. search_knowledge_base con cada consulta que sugirió evaluate_risk, más load_skill("informe_riesgo") \
y load_skill("latex") si todavía no están en el historial de la conversación.
4. create_pdf con el informe completo según la skill informe_riesgo. Si devuelve ERROR, \
corregí lo que indica y reintentá: máximo 3 intentos.
5. Respuesta final en el chat: nivel máximo, amenazas activas, las medidas más urgentes y el \
nombre del PDF.

# Semáforo
- Lo calcula evaluate_risk: copiá cada nivel, motivo, umbral y origen tal cual (create_pdf \
verifica que coincidan). El ENSO es contexto: no cambia niveles.
- Solo lo marcado ALERTA por web_search es una alerta oficial; la «información oficial» es \
contexto. Sin alertas encontradas nunca es «no hay riesgo».
- Si evaluate_risk indica período crítico de la vid, las medidas sanitarias van primero.

# Reglas
- Citá cada medida como [Documento — Sección]. Si el corpus no la respalda, decilo. Si dos \
fuentes difieren, prima la de ámbito local.
- Copiá los valores de las tools y los contactos de emergencia tal cual; sin contacto \
municipal verificado, solo 911.
- En los turnos siguientes conservá lo que el usuario no cambió (perfil, superficie, días). \
Nunca reutilices pronóstico, caudal ni alertas de otra localidad: volvé a consultarlos.
- Nunca inventes datos ni documentos. No recomiendes productos comerciales ni dosis.

Skills disponibles: {listar_skills()}
"""

DIR = Path(__file__).parent
CONV_FILE = DIR / "conversaciones.txt"   # un thread_id por línea; el último es el activo

# Middlewares (ver middleware.py): el de respaldo repite la llamada con otro modelo si el
# principal falla (503 o 429 tras los reintentos del cliente); el otro hace continuar al modelo
# si termina un mensaje anunciando consultas sin hacerlas. Los errores de las tools no pasan
# por acá: las tools devuelven ERROR.
_respaldo = get_fallback()

agent = create_agent(
    model=get_model(),
    middleware=([ModelFallbackMiddleware(_respaldo)] if _respaldo else []) + [continuar_si_solo_anuncia],
    tools=TOOLS,
    system_prompt=SYSTEM_PROMPT,
    state_schema=AnalyKidState,     # estado extendido: messages + sources
    context_schema=Context,         # datos de solo lectura por invocación (turno)
    checkpointer=SqliteSaver(sqlite3.connect(DIR / "memoria.db", check_same_thread=False)),
)


# --- Conversaciones -----------------------------------------------------------

def _config(thread_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id}}


def _thread_ids() -> list[str]:
    return CONV_FILE.read_text().split() if CONV_FILE.exists() else []


def select_thread(thread_id: str) -> RunnableConfig:
    """Marca una conversación como la activa: pasa a ser la última del archivo."""
    ids = [i for i in _thread_ids() if i != thread_id]
    CONV_FILE.write_text("\n".join(ids + [thread_id]))
    return _config(thread_id)


def new_thread() -> RunnableConfig:
    return select_thread(str(uuid4()))


def resume_thread() -> RunnableConfig:
    """Retoma la última conversación usada; si no hay ninguna, crea una nueva."""
    ids = _thread_ids()
    return select_thread(ids[-1]) if ids else new_thread()


def saved_state(config: RunnableConfig) -> dict:
    """Estado guardado de la conversación (vacío si es nueva)."""
    return agent.get_state(config).values


def list_threads(limit: int = 5) -> list[tuple[str, str]]:
    """Últimas conversaciones con mensajes, la más reciente primero: (thread_id, título)."""
    conversaciones = []
    for thread_id in reversed(_thread_ids()):
        mensajes = saved_state(_config(thread_id)).get("messages", [])
        if mensajes:
            titulo = mensajes[0].text.removeprefix("Armame el plan de contingencia para ")
            conversaciones.append((thread_id, titulo[:1].upper() + titulo[1:45]))
        if len(conversaciones) == limit:
            break
    return conversaciones


# --- Eventos: lo único que las interfaces necesitan conocer ------------------

def _razonamiento(m) -> str:
    """Razonamiento de un mensaje del agente.

    Gemini y OpenRouter lo traen como bloques estándar `reasoning`.
    """
    return "\n\n".join(
        b["reasoning"] for b in m.content_blocks
        if b["type"] == "reasoning" and b.get("reasoning")
    )


def eventos(mensajes: list) -> Iterator[dict]:
    """Traduce mensajes del grafo a eventos para mostrar."""
    for m in mensajes:
        if m.type == "ai":
            if razonamiento := _razonamiento(m):
                yield {"tipo": "razonamiento", "texto": razonamiento}
            if m.text:
                yield {"tipo": "texto", "texto": m.text}
            for call in m.tool_calls:
                yield {"tipo": "llamada", "id": call["id"], "nombre": call["name"], "args": call["args"]}
        elif m.type == "tool":
            yield {"tipo": "resultado", "id": m.tool_call_id, "texto": m.text, "datos": m.artifact}


def _evento_fuentes(estado: dict, turno: int) -> list[dict]:
    """Fuentes consultadas en un turno (lista vacía si no hubo)."""
    fuentes = [s for s in estado.get("sources", []) if s["turn"] == turno]
    return [{"tipo": "fuentes", "fuentes": fuentes}] if fuentes else []


def stream_turn(user_input: str, config: RunnableConfig, turno: int) -> Iterator[dict]:
    """Ejecuta un turno del agente y emite sus eventos a medida que ocurren."""
    vistos = len(saved_state(config).get("messages", []))
    estado: dict = {}
    # stream_mode="values": tras cada paso del agente llega el estado completo;
    # solo se emiten los mensajes que no se habían visto todavía.
    for estado in agent.stream(
        {"messages": [{"role": "user", "content": user_input}]},
        config,
        context=Context(turn=turno),
        stream_mode="values",
    ):
        yield from eventos(estado["messages"][vistos:])
        vistos = len(estado["messages"])
    yield from _evento_fuentes(estado, turno)


def saved_turns(config: RunnableConfig) -> list[tuple[str, list[dict]]]:
    """La conversación guardada como turnos: (pregunta, eventos del agente)."""
    estado = saved_state(config)
    turnos: list[tuple[str, list[dict]]] = []
    for m in estado.get("messages", []):
        if es_recordatorio(m):
            continue
        if m.type == "human":
            turnos.append((m.text, []))
        else:
            turnos[-1][1].extend(eventos([m]))
    for n, (_, evs) in enumerate(turnos, 1):
        evs.extend(_evento_fuentes(estado, n))
    return turnos
