"""get_river_discharge: caudal previsto (GloFAS, Flood API) contra la media 1991-2020.

El punto de cada río sale de datos/rios.json y la media histórica de
datos/climatologia/<rio>.json (scripts/calcular_climatologia.py). No se usa
`river_discharge_mean` de la API: es la media del ensamble, no la histórica.
"""
import json
from datetime import date
from typing import Annotated, Literal

from langchain.tools import ToolRuntime, tool
from langgraph.types import Command
from pydantic import Field

from tools.common import DATOS_DIR, Context, cargar_json, error, pedir, respond

URL = "https://flood-api.open-meteo.com/v1/flood"
UMBRAL_TENDENCIA = 0.10   # variación relativa entre el primer y el último día


def media_del_dia(medias_por_dia: list, iso: str) -> float | None:
    """Media 1991-2020 de una fecha (índice con calendario bisiesto: el 29/2 es el 59)."""
    d = date.fromisoformat(iso)
    return medias_por_dia[(date(2000, d.month, d.day) - date(2000, 1, 1)).days]


def media_historica(medias_por_dia: list, fechas: list[str]) -> float | None:
    """Promedio de la media 1991-2020 de las fechas del período."""
    valores = [v for f in fechas if (v := media_del_dia(medias_por_dia, f)) is not None]
    return sum(valores) / len(valores) if valores else None


def tendencia(caudales: list[float]) -> str:
    inicio, fin = caudales[0], caudales[-1]
    if inicio <= 0:
        return "sube" if fin > 0 else "estable"
    cambio = (fin - inicio) / inicio
    return "sube" if cambio > UMBRAL_TENDENCIA else "baja" if cambio < -UMBRAL_TENDENCIA else "estable"


def calcular(fechas: list[str], caudales: list, medias_por_dia: list) -> dict | None:
    """Caudal máximo y fecha, media histórica del período, cociente y tendencia."""
    pares = [(f, q) for f, q in zip(fechas, caudales) if q is not None]
    media = media_historica(medias_por_dia, [f for f, _ in pares])
    if not pares or not media:
        return None
    f_max, q_max = max(pares, key=lambda p: p[1])
    return {
        "caudal_max_m3s": round(q_max), "fecha_max": f_max,
        "media_1991_2020_m3s": round(media),
        "cociente": round(q_max / media, 2),
        "tendencia": tendencia([q for _, q in pares]),
        "serie": [{"fecha": f, "caudal_m3s": round(q, 1),
                   "media_1991_2020_m3s": media_del_dia(medias_por_dia, f)} for f, q in pares],
    }


@tool
def get_river_discharge(
    rio: Literal["mendoza", "tunuyan", "diamante", "atuel"],
    runtime: ToolRuntime[Context],
    dias: Annotated[int, Field(ge=1, le=30)] = 7,
) -> Command:
    """Caudal previsto de un río de Mendoza comparado con su media histórica 1991-2020
    para las mismas fechas: caudal máximo y fecha, media, cociente máximo/media (el
    indicador de crecida) y tendencia. Usá el río de la localidad que informa
    get_weather_forecast. Es caudal simulado (GloFAS): no modela los embalses.
    """
    punto = cargar_json("rios.json")["rios"][rio]
    try:
        clima = json.loads((DATOS_DIR / "climatologia" / f"{rio}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return respond(runtime, error(
            "get_river_discharge", f"falta la climatología de «{rio}»",
            "Seguí sin caudal: la amenaza de crecida va como «sin datos»."))

    datos, causa = pedir(URL, {
        "latitude": punto["consulta"]["latitud"], "longitude": punto["consulta"]["longitud"],
        "daily": "river_discharge", "forecast_days": dias,
    })
    if causa:
        return respond(runtime, error(
            "get_river_discharge", f"Flood API: {causa}",
            "Seguí sin caudal: la amenaza de crecida va como «sin datos»."))
    try:
        r = calcular(datos["daily"]["time"], datos["daily"]["river_discharge"],
                     clima["media_por_dia_del_anio"])
    except (KeyError, TypeError, ValueError, IndexError):
        r = None
    if r is None:
        return respond(runtime, error(
            "get_river_discharge", "la Flood API no devolvió caudales para ese punto",
            "Seguí sin caudal: la amenaza de crecida va como «sin datos»."))

    verificado = f"verificado {punto['verificado']}" if punto.get("verificado") else "punto sin verificar"
    texto = (
        f"Caudal {punto['nombre']} ({rio}), {len(r['serie'])} días, GloFAS en "
        f"{punto['estacion_referencia']} ({verificado}): máximo {r['caudal_max_m3s']} m³/s el "
        f"{date.fromisoformat(r['fecha_max']).strftime('%d/%m')}; media 1991-2020 del período "
        f"{r['media_1991_2020_m3s']} m³/s; cociente máximo/media {r['cociente']}; tendencia "
        f"{r['tendencia']}. Simulado: no incluye la regulación de los embalses."
    )
    fuente = {"turn": runtime.context.turn, "title": f"Open-Meteo Flood API (GloFAS): {punto['nombre']}",
              "url": "https://open-meteo.com/en/docs/flood-api"}
    return respond(runtime, texto, artifact={"rio": rio, **r}, sources=[fuente])
