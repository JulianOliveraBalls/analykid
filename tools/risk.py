"""evaluate_risk: semáforo por amenaza, etapa del cultivo y guía para el informe.

No recibe datos del modelo: lee del estado los resultados del turno de
get_weather_forecast, get_river_discharge y web_search, y aplica en código la
tabla de umbrales. Así el modelo copia los niveles en lugar de calcularlos, y el
PDF y la UI muestran siempre lo mismo. Además devuelve la etapa fenológica, los
días críticos, los disparadores de escalamiento y qué consultar en el RAG.
"""
import re
from datetime import date
from typing import Literal

from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from tools.common import Context, cargar_json, error, respond, resultados_del_turno

NIVELES = ["verde", "amarillo", "naranja", "rojo"]
SIN_DATOS, NO_APLICA = "sin datos", "no aplica"
AMENAZAS = ["Pluvial", "Granizo / tormenta", "Aluvional", "Crecida", "Sanitaria"]

UMBRALES = {   # amarillo, naranja, rojo
    "Pluvial": (10, 25, 50),
    "Granizo / tormenta": (1000, 2000, 3000),
    "Crecida": (1.5, 2.0, 3.0),
    "Sanitaria": (1, 2, 3),
}
ALUVIONAL = ((10, 1000), (20, 1500), (35, 2000))   # (lluvia mm, CAPE J/kg) por nivel
PROB_SUBE_GRANIZO = 60
MAX_CONSULTAS = 6

# Palabras de una alerta oficial que indican a qué amenaza se refiere.
ALERTA_AMENAZA = {
    "Granizo / tormenta": r"tormenta|granizo|piedra|eléctric",
    "Pluvial": r"lluvia|precipitaci",
    "Aluvional": r"aluvi",
    "Crecida": r"crecida|creciente|caudal",
}
ALERTA_COLOR = {"amarill": 1, "naranja": 2, "roj": 3}

CONSULTAS = {
    "Pluvial": "preparación de la finca ante lluvias intensas, drenaje y anegamiento",
    "Granizo / tormenta": "malla antigranizo y manejo de la vid después del granizo",
    "Tormenta eléctrica": "trabajo en el campo con tormentas eléctricas, cuándo cortar y refugio",
    "Aluvional": "aluvión en piedemonte, señales de alerta y evacuación",
    "Crecida": "crecida de río, canales y acequias en la finca",
    "Sanitaria": "peronóspora de la vid, tratamiento preventivo antes de la lluvia",
    "Temporada": "temporada El Niño 2026-2027 en Mendoza, caudales y riesgos",
}


def _fecha(iso: str | None) -> str:
    return f"{iso[8:10]}/{iso[5:7]}" if iso else "s/d"


def _nivel(valor, umbrales) -> int:
    return sum(valor >= u for u in umbrales)


def _amenaza(nombre: str, n: int | str, motivo: str, umbral: str, origen: str) -> dict:
    nivel = NIVELES[n] if isinstance(n, int) else n
    return {"amenaza": nombre, "nivel": nivel, "motivo": motivo, "umbral": umbral, "origen": origen}


def _umbral_texto(nombre: str, n: int, unidad: str) -> str:
    u = UMBRALES[nombre]
    return f"≥ {u[n - 1]}{unidad}" if n else f"< {u[0]}{unidad}"


def evaluar(pron: dict | None, caudal: dict | None, perfil: str | None = None) -> list[dict]:
    """Las cinco amenazas con nivel, motivo, umbral aplicado y origen del dato."""
    resultado = []
    if pron is None:
        resultado += [_amenaza(a, SIN_DATOS, "El pronóstico no está disponible", "—", "—")
                      for a in AMENAZAS[:3]]
    else:
        i = pron["indicadores"]
        lluvia, cape = i["lluvia_max_mm"] or 0, i["cape_max_jkg"] or 0

        n = _nivel(lluvia, UMBRALES["Pluvial"])
        resultado.append(_amenaza("Pluvial", n, f"Lluvia máx. {lluvia} mm el {_fecha(i['fecha_lluvia_max'])}",
                                  _umbral_texto("Pluvial", n, " mm"), "Open-Meteo"))

        n = _nivel(cape, UMBRALES["Granizo / tormenta"])
        motivo = f"CAPE máx. {cape} J/kg el {_fecha(i['fecha_cape_max'])}"
        if n and (i["prob_dia_cape_max_pct"] or 0) >= PROB_SUBE_GRANIZO:
            n = min(n + 1, 3)
            motivo += f", prob. {i['prob_dia_cape_max_pct']} % ese día (sube un nivel)"
        resultado.append(_amenaza("Granizo / tormenta", n, motivo,
                                  _umbral_texto("Granizo / tormenta", _nivel(cape, UMBRALES["Granizo / tormenta"]), " J/kg"),
                                  "Open-Meteo"))

        n = sum(lluvia >= ll and cape >= c for ll, c in ALUVIONAL)
        motivo = f"Lluvia máx. {lluvia} mm y CAPE máx. {cape} J/kg"
        if not pron.get("piedemonte") and n > 1:
            n, motivo = 1, motivo + " (fuera del piedemonte: máximo amarillo)"
        umbral = (f"≥ {ALUVIONAL[n - 1][0]} mm y ≥ {ALUVIONAL[n - 1][1]} J/kg" if n
                  else f"< {ALUVIONAL[0][0]} mm o < {ALUVIONAL[0][1]} J/kg")
        resultado.append(_amenaza("Aluvional", n, motivo, umbral, "Open-Meteo"))

    if caudal is None:
        resultado.append(_amenaza("Crecida", SIN_DATOS, "El caudal no está disponible", "—", "—"))
    else:
        n = _nivel(caudal["cociente"], UMBRALES["Crecida"])
        resultado.append(_amenaza("Crecida", n, f"Caudal máx. {caudal['cociente']} veces la media 1991-2020",
                                  _umbral_texto("Crecida", n, ""), "GloFAS"))

    if perfil == "urbano":
        resultado.append(_amenaza("Sanitaria", NO_APLICA, "No aplica al perfil urbano", "—", "—"))
    elif pron is None:
        resultado.append(_amenaza("Sanitaria", SIN_DATOS, "El pronóstico no está disponible", "—", "—"))
    else:
        dias = pron["indicadores"]["dias_favorables_hongos"]
        n = _nivel(dias, UMBRALES["Sanitaria"])
        resultado.append(_amenaza("Sanitaria", n, f"{dias} día(s) con ≥ 10 mm y mínima ≥ 10 °C",
                                  _umbral_texto("Sanitaria", n, " día(s)"), "Open-Meteo, regla 10:10:24"))
    return resultado


def aplicar_alertas(amenazas: list[dict], alertas: dict | None) -> list[dict]:
    """Una alerta oficial vigente fija el nivel mínimo de la amenaza a la que se refiere."""
    for a in (alertas or {}).get("elegidos", []):
        if not a.get("es_alerta"):
            continue
        texto = f"{a.get('titulo', '')} {a.get('resumen', '')}".lower()
        color = max((n for k, n in ALERTA_COLOR.items() if k in texto), default=1)
        afectadas = [nombre for nombre, patron in ALERTA_AMENAZA.items() if re.search(patron, texto)]
        for am in amenazas:
            if am["amenaza"] not in (afectadas or ["Granizo / tormenta"]) or am["nivel"] not in NIVELES:
                continue
            actual = NIVELES.index(am["nivel"])
            if color > actual:
                am["nivel"] = NIVELES[color]
                am["motivo"] += f"; fijado por alerta oficial ({a['dominio']})"
                am["origen"] = f"alerta oficial {a['dominio']}"
            elif actual > 0:
                am["motivo"] += "; señal del pronóstico por encima de la alerta oficial vigente"
    for am in amenazas:
        if am["nivel"] in NIVELES[1:] and "alerta oficial" not in am["motivo"]:
            am["motivo"] += "; señal del pronóstico, sin alerta oficial vigente"
    return amenazas


def nivel_maximo(amenazas: list[dict]) -> str:
    niveles = [NIVELES.index(a["nivel"]) for a in amenazas if a["nivel"] in NIVELES]
    return NIVELES[max(niveles)] if niveles else SIN_DATOS


def etapa_fenologica(oasis: str | None, perfil: str | None, hoy: date) -> dict | None:
    """Etapa aproximada del cultivo y si está en el período crítico de peronóspora."""
    datos = cargar_json("fenologia.json")
    if perfil not in datos["perfiles"] or oasis not in datos["oasis"]:
        return None
    calendario = datos["oasis"][oasis]
    md = hoy.strftime("%m-%d")
    etapas = sorted(calendario["etapas"], key=lambda e: e[1])
    actual = next((nombre for nombre, desde in reversed(etapas) if md >= desde), etapas[-1][0])
    inicio, fin = calendario["periodo_critico"]
    return {"etapa": actual, "periodo_critico": inicio <= md <= fin,
            "periodo_critico_texto": f"{inicio[3:]}/{inicio[:2]} al {fin[3:]}/{fin[:2]}",
            "nota": calendario.get("nota", "Fechas aproximadas.")}


def dias_criticos(pron: dict | None) -> list[dict]:
    """Días en que algún indicador diario alcanza el umbral amarillo."""
    if pron is None:
        return []
    criticos = []
    for d in pron["dias"]:
        motivos = []
        if (d["lluvia_mm"] or 0) >= UMBRALES["Pluvial"][0]:
            motivos.append(f"lluvia {d['lluvia_mm']} mm")
        if (d["cape_jkg"] or 0) >= UMBRALES["Granizo / tormenta"][0]:
            motivos.append(f"CAPE {d['cape_jkg']} J/kg (prob. {d['prob_pct']} %)")
        if (d["lluvia_mm"] or 0) >= 10 and (d["tmin_c"] or -99) >= 10:
            motivos.append("favorable a hongos")
        if motivos:
            criticos.append({"fecha": d["fecha"], "motivos": motivos})
    return criticos


def escalamiento(amenazas: list[dict]) -> list[str]:
    """Para cada amenaza activa, qué haría subir su nivel (siguiente umbral o alerta oficial)."""
    siguiente = {
        "Pluvial": lambda n: f"lluvia diaria prevista ≥ {UMBRALES['Pluvial'][n]} mm",
        "Granizo / tormenta": lambda n: f"CAPE ≥ {UMBRALES['Granizo / tormenta'][n]} J/kg",
        "Aluvional": lambda n: f"lluvia ≥ {ALUVIONAL[n][0]} mm con CAPE ≥ {ALUVIONAL[n][1]} J/kg",
        "Crecida": lambda n: f"caudal ≥ {UMBRALES['Crecida'][n]} veces la media",
        "Sanitaria": lambda n: f"{UMBRALES['Sanitaria'][n]} días favorables a hongos",
    }
    reglas = []
    for a in amenazas:
        if a["nivel"] not in NIVELES or a["nivel"] == "rojo":
            continue
        n = NIVELES.index(a["nivel"])
        if a["amenaza"] == "Aluvional" and "fuera del piedemonte" in a["motivo"]:
            continue
        reglas.append(f"{a['amenaza']}: pasa a {NIVELES[n + 1]} si {siguiente[a['amenaza']](n)} "
                      f"o si se emite una alerta oficial {NIVELES[n + 1]}.")
    return reglas


def consultas_sugeridas(amenazas: list[dict], etapa: dict | None, perfil: str | None) -> list[str]:
    """Qué buscar en el RAG, de la amenaza más grave a la menos grave, más la temporada."""
    activas = sorted((a for a in amenazas if a["nivel"] in NIVELES[1:]),
                     key=lambda a: -NIVELES.index(a["nivel"]))
    nombres = [a["amenaza"] for a in activas]
    if etapa and etapa["periodo_critico"] and "Sanitaria" not in nombres:
        nombres.append("Sanitaria")
    if etapa and etapa["periodo_critico"] and "Sanitaria" in nombres:
        nombres.insert(0, nombres.pop(nombres.index("Sanitaria")))   # prioridad sanitaria
    consultas = []
    for n in nombres:
        if n == "Sanitaria" and perfil != "vid":
            continue
        consultas.append(CONSULTAS[n])
        if n == "Granizo / tormenta":
            consultas.append(CONSULTAS["Tormenta eléctrica"])
    consultas.append(CONSULTAS["Temporada"])
    return list(dict.fromkeys(consultas))[:MAX_CONSULTAS]


def evaluar_turno(resultados: dict, perfil: str, hoy: date) -> dict:
    """Todo lo que devuelve evaluate_risk, a partir de los resultados del turno."""
    pron = resultados.get("get_weather_forecast")
    caudal = resultados.get("get_river_discharge")
    amenazas = aplicar_alertas(evaluar(pron, caudal, perfil), resultados.get("web_search"))
    etapa = etapa_fenologica(pron.get("oasis_clave") if pron else None, perfil, hoy)
    criticos = dias_criticos(pron)
    lluvia_fuerte = pron is not None and (pron["indicadores"]["lluvia_max_mm"] or 0) >= UMBRALES["Pluvial"][0]
    crecida = next(a for a in amenazas if a["amenaza"] == "Crecida")
    return {
        "localidad": pron["nombre"] if pron else None,
        "perfil": perfil,
        "amenazas": amenazas,
        "nivel_maximo": nivel_maximo(amenazas),
        "etapa": etapa,
        "dias_criticos": criticos,
        "escalamiento": escalamiento(amenazas),
        "consultas": consultas_sugeridas(amenazas, etapa, perfil),
        "destacar_lluvia_y_canales": crecida["nivel"] in NIVELES[1:] and lluvia_fuerte,
    }


def redactar(r: dict) -> str:
    lineas = [f"Semáforo {r['localidad'] or ''} (perfil {r['perfil']}), nivel máximo {r['nivel_maximo']}:"]
    lineas += [f"- {a['amenaza']}: {a['nivel'].upper()} · {a['motivo']} (umbral {a['umbral']}; {a['origen']})"
               for a in r["amenazas"]]
    if r["etapa"]:
        e = r["etapa"]
        lineas.append(f"Etapa de la vid (aprox.): {e['etapa']}; período crítico de peronóspora "
                      f"{e['periodo_critico_texto']}: {'SÍ, las medidas sanitarias van primero' if e['periodo_critico'] else 'no'}. {e['nota']}")
    if r["dias_criticos"]:
        lineas.append("Días críticos: " + "; ".join(
            f"{_fecha(d['fecha'])} {', '.join(d['motivos'])}" for d in r["dias_criticos"]))
    if r["destacar_lluvia_y_canales"]:
        lineas.append("Destacar: crecida con lluvia intensa prevista (lluvia + canales con agua).")
    if r["escalamiento"]:
        lineas.append("Escalamiento: " + " ".join(r["escalamiento"]))
    lineas.append("Consultas para search_knowledge_base (pedilas en paralelo): "
                  + " | ".join(f"«{c}»" for c in r["consultas"]))
    lineas.append("Copiá estos niveles tal cual en el informe: create_pdf los verifica.")
    return "\n".join(lineas)


@tool
def evaluate_risk(perfil: Literal["vid", "frutal", "hortaliza", "urbano"],
                  runtime: ToolRuntime[Context]) -> Command:
    """Calcula el semáforo de las cinco amenazas con los resultados de este turno de
    get_weather_forecast, get_river_discharge y web_search (no hace falta pasarle
    datos). Devuelve nivel, motivo y umbral de cada amenaza, la etapa del cultivo,
    los días críticos, los disparadores de escalamiento y qué buscar en la base de
    conocimiento. Llamala después de esas tres tools y antes de escribir el informe.
    """
    resultados = resultados_del_turno(runtime.state.get("messages", []))
    if "get_weather_forecast" not in resultados and "get_river_discharge" not in resultados:
        return respond(runtime, error(
            "evaluate_risk", "no hay pronóstico ni caudal en este turno",
            "Llamá primero get_weather_forecast, get_river_discharge y web_search."))
    r = evaluar_turno(resultados, perfil, date.today())
    return respond(runtime, redactar(r), artifact=r)
