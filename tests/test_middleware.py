"""Tests del middleware que hace continuar al modelo cuando anuncia y no actúa."""
from langchain.messages import AIMessage, HumanMessage, ToolMessage

from middleware import RECORDATORIO, necesita_recordatorio
from tools.common import es_recordatorio, resultados_del_turno

PEDIDO = HumanMessage("Armame el plan para Tupungato")
ANUNCIO = AIMessage("Voy a consultar el pronóstico y el caudal.")


def _recordatorio():
    return HumanMessage(RECORDATORIO, additional_kwargs={"recordatorio": True})


def test_anuncio_sin_llamadas_pide_continuar():
    assert necesita_recordatorio([PEDIDO, ANUNCIO])


def test_no_interviene_si_hay_llamadas_pregunta_o_respuesta_final():
    con_llamada = AIMessage("Voy a consultar.", tool_calls=[{"id": "a", "name": "get_enso_status", "args": {}}])
    assert not necesita_recordatorio([PEDIDO, con_llamada])
    assert not necesita_recordatorio([PEDIDO, AIMessage("¿En qué localidad está la finca?")])
    final = [PEDIDO, AIMessage("", tool_calls=[{"id": "p", "name": "create_pdf", "args": {}}]),
             ToolMessage("PDF creado: plan.pdf", tool_call_id="p"), AIMessage("Listo. Voy a resumir:")]
    assert not necesita_recordatorio(final)
    assert not necesita_recordatorio([PEDIDO, AIMessage("No pude generar el PDF.")])


def test_maximo_dos_recordatorios_por_turno():
    assert necesita_recordatorio([PEDIDO, ANUNCIO, _recordatorio(), ANUNCIO])
    assert not necesita_recordatorio([PEDIDO, ANUNCIO, _recordatorio(), ANUNCIO, _recordatorio(), ANUNCIO])


def test_el_recordatorio_no_corta_el_turno_al_leer_resultados():
    mensajes = [PEDIDO, AIMessage("", tool_calls=[{"id": "w", "name": "get_weather_forecast", "args": {}}]),
                ToolMessage("ok", tool_call_id="w", artifact={"nombre": "Tupungato"}), ANUNCIO, _recordatorio()]
    assert es_recordatorio(mensajes[-1]) and not es_recordatorio(PEDIDO)
    assert resultados_del_turno(mensajes) == {"get_weather_forecast": {"nombre": "Tupungato"}}
