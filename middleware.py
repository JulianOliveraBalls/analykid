"""Middleware propio del agente: continuar cuando el modelo anuncia y no actúa.

Flash Lite a veces termina un mensaje anunciando una consulta («Voy a consultar…») sin hacer
las llamadas, y el turno se corta sin informe (pasó 2 de 6 veces en las pruebas, con la misma
entrada). Si el modelo termina así, sin PDF todavía y sin estar preguntándole algo al usuario,
se agrega un recordatorio y se vuelve al modelo, hasta 2 veces por turno. El recordatorio queda
en el historial marcado como interno y la UI no lo muestra.
"""
import re

from langchain.agents.middleware import after_model
from langchain.messages import HumanMessage

from tools.common import AnalyKidState, es_recordatorio

RECORDATORIO = "Continuá: hacé ahora, en este mensaje, las llamadas a las tools que anunciaste."
# También el futuro en primera persona («Consultaré…», «Generaré…», «Evaluaremos…»): Flash Lite
# lo usa seguido para anunciar y el turno se cortaba igual. Algunos pretéritos coinciden
# («generé»), pero solo se interviene sin tools, sin PDF creado y hasta 2 veces: es inofensivo.
ANUNCIO = re.compile(r"\b(voy a|vamos a|ahora (voy|consulto|busco|genero)|procedo"
                     r"|\w+(aré|eré|iré|aremos|eremos|iremos))\b", re.IGNORECASE)
MAX_RECORDATORIOS = 2


def necesita_recordatorio(mensajes: list) -> bool:
    ultimo = mensajes[-1]
    if ultimo.type != "ai" or ultimo.tool_calls or ultimo.text.rstrip().endswith("?"):
        return False
    if not ANUNCIO.search(ultimo.text):
        return False
    inicio = max((i for i, m in enumerate(mensajes) if m.type == "human" and not es_recordatorio(m)),
                 default=-1)
    turno = mensajes[inicio + 1:]
    if any(m.type == "tool" and str(m.content).startswith("PDF creado") for m in turno):
        return False
    return sum(es_recordatorio(m) for m in turno) < MAX_RECORDATORIOS


@after_model(can_jump_to=["model"])
def continuar_si_solo_anuncia(state: AnalyKidState, runtime) -> dict | None:
    if not necesita_recordatorio(state["messages"]):
        return None
    return {"messages": [HumanMessage(RECORDATORIO, additional_kwargs={"recordatorio": True})],
            "jump_to": "model"}
