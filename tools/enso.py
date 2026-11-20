"""get_enso_status: estado de El Niño / La Niña según el índice RONI de NOAA.

El RONI (Relative Oceanic Niño Index) es el índice oficial de NOAA desde 2026.
El valor va con 2 decimales, como lo publica NOAA: con 1 decimal, +1.97 (fuerte)
se leería +2.0 (muy fuerte).
Orden de lectura: caché del día (datos/cache/) → descarga → caché vieja →
respaldo versionado (datos/respaldo/). El texto siempre dice qué dato usó.
"""
import time
from typing import Annotated

from langchain.tools import ToolRuntime, tool
from langgraph.types import Command
from pydantic import Field

from tools.common import DATOS_DIR, Context, error, pedir, respond

URL = "https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt"
ARCHIVO = "RONI.ascii.txt"
CACHE = DATOS_DIR / "cache" / ARCHIVO
RESPALDO = DATOS_DIR / "respaldo" / ARCHIVO
CACHE_VIGENTE_S = 24 * 3600
UMBRAL = 0.5            # |índice| ≥ 0,5 → El Niño / La Niña
TRIMESTRES_EPISODIO = 5  # trimestres móviles consecutivos sobre el umbral para un episodio
MESES = {"DJF": "dic-feb", "JFM": "ene-mar", "FMA": "feb-abr", "MAM": "mar-may",
         "AMJ": "abr-jun", "MJJ": "may-jul", "JJA": "jun-ago", "JAS": "jul-sep",
         "ASO": "ago-oct", "SON": "sep-nov", "OND": "oct-dic", "NDJ": "nov-ene"}


def parsear(texto: str) -> list[tuple[str, int, float]]:
    """Filas (trimestre, año, anomalía) del archivo de NOAA; la anomalía es la última columna."""
    filas = []
    for linea in texto.splitlines():
        partes = linea.split()
        if len(partes) >= 3 and partes[0] in MESES:
            filas.append((partes[0], int(partes[1]), float(partes[-1])))
    return filas


def fase(valor: float) -> str:
    return "El Niño" if valor >= UMBRAL else "La Niña" if valor <= -UMBRAL else "Neutral"


def categoria(valor: float) -> str:
    v = abs(valor)
    if v < UMBRAL:
        return "sin evento"
    return "débil" if v < 1.0 else "moderado" if v < 1.5 else "fuerte" if v < 2.0 else "muy fuerte"


def trimestres_consecutivos(valores: list[float]) -> int:
    """Trimestres al final de la serie en la misma fase (≠ Neutral) que el último."""
    actual, n = fase(valores[-1]), 0
    for v in reversed(valores):
        if actual == "Neutral" or fase(v) != actual:
            break
        n += 1
    return n


def resumir(filas: list[tuple[str, int, float]], trimestres: int) -> dict:
    valores = [v for _, _, v in filas]
    seas, anio, valor = filas[-1]
    anterior = valores[-2] if len(valores) > 1 else valor
    delta = valor - anterior
    consecutivos = trimestres_consecutivos(valores)
    return {
        "trimestre": f"{seas} {anio} ({MESES[seas]})",
        "valor": round(valor, 2), "fase": fase(valor), "categoria": categoria(valor),
        "tendencia": "sube" if delta >= 0.1 else "baja" if delta <= -0.1 else "estable",
        "trimestres_consecutivos": consecutivos,
        "episodio": consecutivos >= TRIMESTRES_EPISODIO,
        "serie": [{"trimestre": f"{s} {a}", "valor": round(v, 2)} for s, a, v in filas[-trimestres:]],
    }


def _leer(ruta) -> list | None:
    try:
        filas = parsear(ruta.read_text(encoding="utf-8"))
        return filas or None
    except OSError:
        return None


def obtener() -> tuple[list | None, str]:
    """Filas del RONI y de dónde salieron."""
    if CACHE.exists() and time.time() - CACHE.stat().st_mtime < CACHE_VIGENTE_S:
        if filas := _leer(CACHE):
            return filas, "NOAA (descargado hoy)"
    texto, causa = pedir(URL, {})
    if not causa and isinstance(texto, str) and (filas := parsear(texto)):
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(texto, encoding="utf-8")
        return filas, "NOAA (descargado hoy)"
    if filas := _leer(CACHE):
        return filas, "caché local (NOAA no respondió)"
    if filas := _leer(RESPALDO):
        return filas, "respaldo versionado del repo (NOAA no respondió)"
    return None, causa or "archivo sin datos"


@tool
def get_enso_status(
    runtime: ToolRuntime[Context],
    trimestres: Annotated[int, Field(ge=1, le=12)] = 4,
) -> Command:
    """Estado actual de El Niño / La Niña (índice RONI de NOAA): fase, valor,
    categoría, tendencia y si ya es un episodio. Es contexto de la temporada: no
    cambia el nivel de riesgo de cada día. Llamala una vez por conversación.
    `trimestres` (1-12) es cuántos trimestres recientes incluir en la serie.
    """
    filas, origen = obtener()
    if filas is None:
        return respond(runtime, error(
            "get_enso_status", f"no hay datos del índice ({origen})",
            "Seguí sin contexto ENSO y aclaralo en el informe."))

    r = resumir(filas, trimestres)
    episodio = (
        f"episodio en curso ({r['trimestres_consecutivos']} trimestres consecutivos)" if r["episodio"]
        else f"{r['trimestres_consecutivos']} de {TRIMESTRES_EPISODIO} trimestres consecutivos "
             "necesarios para declarar episodio"
    )
    serie = ", ".join(f"{s['trimestre']} {s['valor']:+.2f}" for s in r["serie"])
    texto = (
        f"ENSO (RONI, {origen}): {r['fase']} {r['categoria']}, {r['valor']:+.2f} en {r['trimestre']}; "
        f"tendencia {r['tendencia']}; {episodio}. Serie: {serie}."
    )
    fuente = {"turn": runtime.context.turn, "title": "NOAA CPC: Relative Oceanic Niño Index (RONI)",
              "url": URL}
    return respond(runtime, texto, artifact={"origen": origen, **r}, sources=[fuente])
