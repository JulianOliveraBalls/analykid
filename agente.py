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
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver

from model import get_model
from tools import TOOLS, Context, AnalyKidState, listar_skills

# La fecha se fija al iniciar el programa; no se actualiza si la sesión cruza la medianoche.
HOY = date.today()
MODELO = f"{os.getenv('MODEL_PROVIDER', 'google_genai')} · {os.getenv('MODEL_NAME', 'gemini-2.5-flash')}"

SYSTEM_PROMPT = f"""Sos AnalyKid: armás planes de contingencia en PDF ante el riesgo hídrico y \
climático de fincas y localidades de Mendoza durante El Niño 2026-2027. Respondé en español \
rioplatense, claro y conciso. Hoy es {HOY.strftime("%d/%m/%Y")}; no asumas otro año.

# Datos de la tarea
Necesitás localidad (del catálogo de Mendoza), perfil (vid, frutal, hortaliza o urbano), \
superficie si es una finca, y cantidad de días (7 si no la dicen). Si falta la localidad o el \
perfil, preguntá una sola vez, todo junto. Fuera de alcance: coordenadas libres, Zonda, heladas \
y nieve; si lo piden, decilo y seguí con lo que sí cubrís.

# Flujo
Antes de cada grupo de tools, explicá en 1-2 líneas qué vas a consultar y por qué. Pedí en \
paralelo las tools de un mismo paso.
1. get_weather_forecast y, solo la primera vez en la conversación, get_enso_status y \
load_skill("fuentes_datos").
2. Con el río y la zona de la cabecera del pronóstico: get_river_discharge y web_search.
3. Evaluá el semáforo con la tabla de abajo (no hay tool para esto).
4. search_knowledge_base para cada amenaza en amarillo o más y para el contexto de la \
temporada: máximo 5 consultas, en paralelo.
5. load_skill("informe_riesgo") y load_skill("latex"), salvo que ya estén en el historial.
6. create_pdf con el informe completo. Si falla, corregí y reintentá: máximo 3 intentos.
7. Respuesta final en el chat: resumen breve con el semáforo y el nombre del PDF.

# Semáforo
| Amenaza | Indicador | Amarillo | Naranja | Rojo |
|---|---|---|---|---|
| Pluvial | Lluvia máxima diaria | ≥ 10 mm | ≥ 25 mm | ≥ 50 mm |
| Granizo / tormenta | CAPE máximo | ≥ 1000 J/kg | ≥ 2000 J/kg | ≥ 3000 J/kg |
| Aluvional (solo piedemonte) | Lluvia máx. y CAPE máx. | ≥ 10 mm y ≥ 1000 | ≥ 20 mm y ≥ 1500 | ≥ 35 mm y ≥ 2000 |
| Crecida | Cociente caudal máx. / media | ≥ 1,5 | ≥ 2,0 | ≥ 3,0 |
| Sanitaria (no aplica a urbano) | Días favorables a hongos | 1 | 2 | ≥ 3 |

El umbral sanitario sigue la regla 10:10:24 de la peronóspora; los demás son supuestos del \
equipo y se declaran como tales en el informe.
- Sin umbral alcanzado: verde. Tool con ERROR: «sin datos», nunca verde.
- Granizo: si la probabilidad de precipitación del día del CAPE máximo es ≥ 60 %, sube un \
nivel (máximo rojo).
- Aluvional fuera del piedemonte: máximo amarillo.
- El ENSO es contexto de temporada: no cambia ningún nivel.
- Cada nivel lleva motivo, umbral y origen. Ejemplo: «Naranja: CAPE máx. 2300 J/kg el 18/11 \
(umbral ≥ 2000)».
- Una alerta oficial vigente fija el nivel mínimo. Si los datos dan más, usá el más alto con la \
etiqueta «señal del pronóstico, sin alerta oficial vigente». Nunca llames «alerta» a algo que \
no salió de web_search; sin alertas encontradas nunca es «no hay riesgo».
- Crecida en amarillo o más con lluvia intensa prevista: destacá la combinación lluvia + \
canales con agua (los ríos están regulados por embalses).
- Perfil vid: si la etapa (skill informe_riesgo) está entre brotes de 15-20 cm y baya tamaño \
arveja, las medidas sanitarias van primero; el nivel no cambia.

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

agent = create_agent(
    model=get_model(),
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
            conversaciones.append((thread_id, mensajes[0].text[:40]))
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
        if m.type == "human":
            turnos.append((m.text, []))
        else:
            turnos[-1][1].extend(eventos([m]))
    for n, (_, evs) in enumerate(turnos, 1):
        evs.extend(_evento_fuentes(estado, n))
    return turnos
