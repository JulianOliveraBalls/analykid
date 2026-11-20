"""Tests de evaluate_risk, de la lectura de resultados del turno y del control de create_pdf."""
from datetime import date

from langchain.messages import AIMessage, HumanMessage, ToolMessage

from tools.common import resultados_del_turno
from tools.report import validar
from tools.risk import (aplicar_alertas, consultas_sugeridas, dias_criticos, escalamiento,
                        etapa_fenologica, evaluar, evaluar_turno, nivel_maximo, ventanas)


def _pron(lluvia=0, cape=0, prob=0, hongos=0, piedemonte=True, oasis="valle_de_uco"):
    return {"nombre": "Tupungato", "piedemonte": piedemonte, "oasis_clave": oasis,
            "indicadores": {"lluvia_max_mm": lluvia, "fecha_lluvia_max": "2026-11-24", "cape_max_jkg": cape,
                            "fecha_cape_max": "2026-11-26", "prob_dia_cape_max_pct": prob,
                            "dias_favorables_hongos": hongos},
            "dias": [{"fecha": "2026-11-24", "lluvia_mm": lluvia, "cape_jkg": cape, "prob_pct": prob,
                      "tmin_c": 11.0}]}


def _niveles(amenazas):
    return {a["amenaza"]: a["nivel"] for a in amenazas}


# --- semáforo -------------------------------------------------------------------

def test_todo_verde():
    assert set(_niveles(evaluar(_pron(), {"cociente": 1.0})).values()) == {"verde"}


def test_umbrales_por_amenaza():
    n = _niveles(evaluar(_pron(lluvia=25, cape=2300, prob=10, hongos=3), {"cociente": 3.1}))
    assert n == {"Pluvial": "naranja", "Granizo / tormenta": "naranja", "Aluvional": "naranja",
                 "Crecida": "rojo", "Sanitaria": "rojo"}


def test_un_dia_favorable_a_hongos_es_amarillo():
    # El error del primer PDF: el modelo había puesto verde.
    assert _niveles(evaluar(_pron(hongos=1), None))["Sanitaria"] == "amarillo"


def test_granizo_sube_un_nivel_con_probabilidad_alta():
    assert _niveles(evaluar(_pron(cape=1200, prob=60), None))["Granizo / tormenta"] == "naranja"
    assert _niveles(evaluar(_pron(cape=3500, prob=90), None))["Granizo / tormenta"] == "rojo"
    assert _niveles(evaluar(_pron(cape=500, prob=90), None))["Granizo / tormenta"] == "verde"


def test_aluvional_fuera_del_piedemonte_maximo_amarillo():
    assert _niveles(evaluar(_pron(lluvia=40, cape=2500, piedemonte=False), None))["Aluvional"] == "amarillo"


def test_sin_datos_nunca_es_verde_y_urbano_sin_sanitaria():
    assert set(_niveles(evaluar(None, None)).values()) == {"sin datos"}
    assert nivel_maximo(evaluar(None, None)) == "sin datos"
    assert _niveles(evaluar(_pron(hongos=3), None, "urbano"))["Sanitaria"] == "no aplica"


def test_cada_nivel_trae_umbral_y_origen():
    a = evaluar(_pron(lluvia=12), {"cociente": 0.9})[0]
    assert a["umbral"] == "≥ 10 mm" and a["origen"] == "Open-Meteo"


# --- alertas oficiales ---------------------------------------------------------------

def _alerta(titulo, es_alerta=True):
    return {"elegidos": [{"titulo": titulo, "resumen": "", "dominio": "smn.gob.ar", "es_alerta": es_alerta}]}


def test_alerta_oficial_fija_el_nivel_minimo():
    n = _niveles(aplicar_alertas(evaluar(_pron(), None), _alerta("Alerta naranja por tormentas")))
    assert n["Granizo / tormenta"] == "naranja" and n["Pluvial"] == "verde"


def test_informacion_oficial_no_cambia_niveles():
    n = _niveles(aplicar_alertas(evaluar(_pron(), None), _alerta("Pronóstico: tormentas", False)))
    assert n["Granizo / tormenta"] == "verde"


def test_pronostico_por_encima_de_la_alerta_se_etiqueta():
    a = aplicar_alertas(evaluar(_pron(cape=2500), None), _alerta("Alerta amarilla por tormentas"))
    granizo = next(x for x in a if x["amenaza"] == "Granizo / tormenta")
    assert granizo["nivel"] == "naranja" and "por encima de la alerta oficial" in granizo["motivo"]


def test_sin_alertas_se_etiqueta_senal_del_pronostico():
    a = aplicar_alertas(evaluar(_pron(lluvia=12), None), None)
    assert "señal del pronóstico, sin alerta oficial vigente" in a[0]["motivo"]


# --- etapa, días críticos, escalamiento y consultas -----------------------------------

def test_etapa_de_la_vid_en_valle_de_uco():
    e = etapa_fenologica("valle_de_uco", "vid", date(2026, 11, 20))
    assert e["etapa"] == "floración" and e["periodo_critico"] is True
    assert etapa_fenologica("valle_de_uco", "vid", date(2026, 2, 10))["periodo_critico"] is False
    assert etapa_fenologica("valle_de_uco", "frutal", date(2026, 11, 20)) is None


def test_etapa_en_enero_es_envero_o_bayas():
    assert etapa_fenologica("norte", "vid", date(2027, 1, 20))["etapa"] == "envero"
    assert etapa_fenologica("norte", "vid", date(2026, 6, 1))["etapa"] == "reposo"


def test_dias_criticos():
    criticos = dias_criticos(_pron(lluvia=12, cape=1200, prob=40))
    assert criticos[0]["fecha"] == "2026-11-24" and len(criticos[0]["motivos"]) == 3


def test_escalamiento_da_el_siguiente_umbral():
    reglas = escalamiento(evaluar(_pron(lluvia=12), {"cociente": 0.9}))
    assert any(r.startswith("Pluvial: pasa a naranja si lluvia diaria prevista ≥ 25 mm") for r in reglas)
    assert not any("Aluvional" in r for r in escalamiento(evaluar(_pron(lluvia=40, cape=2500, piedemonte=False), None)))


def test_consultas_priorizan_sanitaria_en_periodo_critico():
    amenazas = evaluar(_pron(lluvia=12, cape=1200), None, "vid")
    etapa = {"periodo_critico": True}
    consultas = consultas_sugeridas(amenazas, etapa, "vid")
    assert consultas[0].startswith("peronóspora") and consultas[-1].startswith("temporada")
    assert len(consultas) <= 7


def test_consultas_conservan_la_temporada_con_todas_las_amenazas_activas():
    amenazas = [{"amenaza": a, "nivel": "rojo"} for a in
                ("Pluvial", "Granizo / tormenta", "Aluvional", "Crecida", "Sanitaria")]
    consultas = consultas_sugeridas(amenazas, None, "vid")
    assert len(consultas) == 7 and consultas[-1].startswith("temporada")
    assert any(c.startswith("qué revisar en cada planta") for c in consultas)


def test_consultas_sin_sanitaria_para_otros_perfiles():
    consultas = consultas_sugeridas(evaluar(_pron(hongos=2), None, "frutal"), None, "frutal")
    assert not any("peronóspora" in c for c in consultas)


def test_evaluar_turno_completo():
    r = evaluar_turno({"get_weather_forecast": _pron(lluvia=12, cape=1210, prob=37, hongos=1),
                       "get_river_discharge": {"cociente": 0.98}}, "vid", date(2026, 11, 20))
    assert r["nivel_maximo"] == "amarillo" and r["etapa"]["etapa"] == "floración"
    assert _niveles(r["amenazas"])["Sanitaria"] == "amarillo"


# --- lectura del estado -----------------------------------------------------------------

def test_resultados_del_turno_toma_solo_el_turno_actual_y_sin_errores():
    mensajes = [
        HumanMessage("turno 1"),
        AIMessage("", tool_calls=[{"id": "a", "name": "get_weather_forecast", "args": {}}]),
        ToolMessage("ok", tool_call_id="a", artifact={"nombre": "Tupungato"}),
        HumanMessage("turno 2"),
        AIMessage("", tool_calls=[{"id": "b", "name": "get_weather_forecast", "args": {}},
                                  {"id": "c", "name": "get_river_discharge", "args": {}}]),
        ToolMessage("ok", tool_call_id="b", artifact={"nombre": "San Rafael"}),
        ToolMessage("ERROR get_river_discharge: x", tool_call_id="c", artifact=None),
    ]
    assert resultados_del_turno(mensajes) == {"get_weather_forecast": {"nombre": "San Rafael"}}


# --- control de create_pdf -----------------------------------------------------------------

RIESGO = {"etapa": None, "amenazas": [
    {"amenaza": "Pluvial", "nivel": "amarillo"}, {"amenaza": "Granizo / tormenta", "nivel": "verde"},
    {"amenaza": "Aluvional", "nivel": "verde"}, {"amenaza": "Crecida", "nivel": "sin datos"},
    {"amenaza": "Sanitaria", "nivel": "verde"}]}
SECCIONES = ["Resumen", "Contexto de temporada", "Pronóstico y días críticos", "Caudal del río",
             "Alertas oficiales y contraste de fuentes", "Semáforo", "Medidas por amenaza", "Escalamiento",
             "Checklist y organización del personal", "Contactos de emergencia", "Fuentes", "Limitaciones"]


def _cuerpo(filas: str, medidas: str) -> str:
    partes = {s: "texto" for s in SECCIONES}
    partes["Semáforo"] = filas
    partes["Medidas por amenaza"] = medidas
    return "\n".join(rf"\section{{{s}}}" + "\n" + c for s, c in partes.items())


FILAS_OK = (r"Pluvial & \nivel{amarillo} & m \\ Granizo/tormenta & \nivel{verde} & m \\ "
            r"Aluvional & \nivel{verde} & m \\ Crecida & \nivel{sindatos} & m \\ Sanitaria & \nivel{verde} & m \\")
MEDIDAS_OK = r"\subsection{Pluvial} \item a [Doc — Sec] \item b [Doc — Otra] \item c [Doc — Tercera]"


def test_informe_completo_pasa():
    assert validar(_cuerpo(FILAS_OK, MEDIDAS_OK), RIESGO) == []


def test_detecta_nivel_distinto_al_de_evaluate_risk():
    problemas = validar(_cuerpo(FILAS_OK.replace(r"Pluvial & \nivel{amarillo}", r"Pluvial & \nivel{verde}"),
                                MEDIDAS_OK), RIESGO)
    assert problemas == ["Pluvial: el semáforo dice verde y evaluate_risk dio amarillo"]


def test_detecta_secciones_faltantes_y_medidas_sin_citas():
    cuerpo = _cuerpo(FILAS_OK, r"\subsection{Pluvial} \item sin cita").replace(r"\section{Escalamiento}", "")
    problemas = validar(cuerpo, RIESGO)
    assert "falta la sección «Escalamiento»" in problemas
    assert any("cita(s)" in p for p in problemas)


def test_alertas_y_contraste_de_fuentes_no_cuenta_como_fuentes():
    cuerpo = _cuerpo(FILAS_OK, MEDIDAS_OK).replace(r"\section{Fuentes}", "")
    assert "falta la sección «Fuentes»" in validar(cuerpo, RIESGO)


def test_etapa_obligatoria_para_vid():
    assert "falta la sección «Etapa»" in validar(_cuerpo(FILAS_OK, MEDIDAS_OK), {**RIESGO, "etapa": {"etapa": "x"}})


# --- ventanas de antes / durante / después ---------------------------------------------

def _pron_semana():
    dias = [{"fecha": f"2026-11-{d}", "lluvia_mm": 0, "cape_jkg": 0, "prob_pct": 0, "tmin_c": 11.0}
            for d in range(20, 27)]
    dias[4].update(lluvia_mm=12.0)            # 24/11
    dias[6].update(cape_jkg=1210)             # 26/11
    return {**_pron(lluvia=12, cape=1210, hongos=1), "dias": dias}


def test_ventanas_por_amenaza_con_fechas():
    pron = _pron_semana()
    v = ventanas(evaluar(pron, None, "vid"), pron, None, date(2026, 11, 20))
    assert v["Pluvial"] == {"antes": "20/11 al 23/11", "durante": "24/11", "despues": "25/11 al 27/11"}
    assert v["Granizo / tormenta"] == {"antes": "20/11 al 25/11", "durante": "26/11", "despues": "27/11 al 29/11"}
    assert v["Sanitaria"]["despues"] == "29/11 al 04/12"        # manchas: 5 a 10 días después
    assert v["Aluvional"]["durante"] == "24/11 y 26/11"


def test_ventana_con_evento_hoy_y_por_alerta():
    pron = _pron_semana()
    pron["dias"][0].update(lluvia_mm=15.0)
    v = ventanas(evaluar(pron, None, "vid"), pron, None, date(2026, 11, 20))
    assert v["Pluvial"]["antes"] == "hoy, 20/11" and v["Pluvial"]["durante"] == "20/11 y 24/11"
    amenazas = aplicar_alertas(evaluar(_pron_semana(), {"cociente": 1.0, "serie": []}),
                               {"elegidos": [{"titulo": "Alerta amarilla por crecida", "resumen": "",
                                              "dominio": "ina.gob.ar", "es_alerta": True}]})
    v = ventanas(amenazas, _pron_semana(), {"serie": []}, date(2026, 11, 20))
    assert v["Crecida"]["durante"] == "mientras rija la alerta oficial"


def test_validar_exige_las_fechas_de_cada_ventana():
    riesgo = {**RIESGO, "ventanas": {"Pluvial": {"antes": "20/11 al 23/11", "durante": "24/11",
                                                 "despues": "25/11 al 27/11"}}}
    problemas = validar(_cuerpo(FILAS_OK, MEDIDAS_OK), riesgo)
    assert "Medidas de Pluvial: falta «Antes (20/11 al 23/11)»" in problemas
    assert validar(_cuerpo(FILAS_OK, _medidas_pluvial()), riesgo) == []


LARGA = "Limpiar acequias y desagües de la finca y sacar ramas y basura para que el agua no anegue las zonas bajas"


def _medidas_pluvial(antes=(LARGA, LARGA), durante=(LARGA,), despues=(LARGA, LARGA)) -> str:
    def bloque(etiqueta, medidas):
        items = " ".join(rf"\item {m} [Doc — Sec {i}]" for i, m in enumerate(medidas))
        return rf"\textbf{{{etiqueta}:}} \begin{{itemize}} {items} \end{{itemize}} "
    return (r"\subsection{Pluvial} " + bloque("Antes (20/11 al 23/11)", antes)
            + bloque("Durante (24/11)", durante) + bloque("Después (25/11 al 27/11)", despues))


def test_validar_exige_medidas_detalladas_en_cada_bloque():
    riesgo = {**RIESGO, "ventanas": {"Pluvial": {"antes": "20/11 al 23/11", "durante": "24/11",
                                                 "despues": "25/11 al 27/11"}}}
    problemas = validar(_cuerpo(FILAS_OK, _medidas_pluvial(antes=(LARGA,), despues=(LARGA, "drenar el agua"))), riesgo)
    assert any(p.startswith("Medidas de Pluvial, Antes: 1 medida(s)") for p in problemas)
    assert any("«drenar el agua» es muy corta" in p for p in problemas)
    assert not any("Durante" in p for p in problemas)
