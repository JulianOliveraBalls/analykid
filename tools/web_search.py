"""web_search: alertas y avisos recientes, solo de dominios oficiales.

Busca con la API de Tavily limitada a datos/dominios_oficiales.json y, además,
descarta en código lo que no sea de esos dominios, no tenga fecha o tenga más
de 48 horas. El modelo solo indica la zona: la consulta la arma la tool.
"""
import os
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from tools.common import Context, cargar_json, error, pedir, respond

URL = "https://api.tavily.com/search"
CANDIDATOS = 8          # se piden más de los que se muestran: el filtro descarta
MAX_RESUMEN = 300
MAX_TEXTO = 1500


def _fecha(texto: str | None) -> datetime | None:
    """Fecha de publicación de Tavily (RFC 2822 o ISO 8601), con zona horaria."""
    if not texto:
        return None
    try:
        d = parsedate_to_datetime(texto)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def dominio_oficial(url: str, dominios: list[str]) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    return next((d for d in dominios if host == d or host.endswith("." + d)), None)


def filtrar(resultados: list[dict], config: dict, ahora: datetime) -> tuple[list[dict], int]:
    """Resultados válidos (los más recientes primero, hasta el máximo) y cantidad de descartados."""
    dominios = [d["dominio"] for d in config["dominios"]]
    limite = ahora - timedelta(hours=config["antiguedad_maxima_horas"])
    validos = []
    for r in resultados:
        dominio, fecha = dominio_oficial(r.get("url", ""), dominios), _fecha(r.get("published_date"))
        if dominio and fecha and limite <= fecha <= ahora + timedelta(hours=1):
            validos.append({"fecha": fecha, "dominio": dominio, "titulo": r.get("title", ""),
                            "resumen": " ".join(r.get("content", "").split())[:MAX_RESUMEN],
                            "url": r["url"]})
    validos.sort(key=lambda r: r["fecha"], reverse=True)
    elegidos = validos[:config["max_resultados"]]
    return elegidos, len(resultados) - len(elegidos)


@tool
def web_search(zona: str, runtime: ToolRuntime[Context]) -> Command:
    """Busca alertas y avisos oficiales vigentes (SMN, Gobierno de Mendoza, Irrigación,
    INA) de las últimas 48 horas para una zona de Mendoza. `zona` es el nombre de la
    localidad o del oasis (por ejemplo «Tupungato» o «Valle de Uco»). No encontrar
    alertas no significa que no haya riesgo.
    """
    config = cargar_json("dominios_oficiales.json")
    clave = os.getenv("TAVILY_API_KEY")
    if not clave:
        return respond(runtime, error(
            "web_search", "falta TAVILY_API_KEY",
            "Seguí sin alertas oficiales y aclaralo en el informe."))

    datos, causa = pedir(URL, cuerpo={
        "query": config["plantilla_consulta"].format(zona=zona),
        "topic": "news", "time_range": "week", "max_results": CANDIDATOS,
        "include_domains": [d["dominio"] for d in config["dominios"]],
    }, headers={"Authorization": f"Bearer {clave}"})
    if causa:
        return respond(runtime, error(
            "web_search", f"Tavily: {causa}", "Seguí sin alertas oficiales y aclaralo en el informe."))

    ahora = datetime.now(timezone.utc)
    resultados = datos.get("results", []) if isinstance(datos, dict) else []
    elegidos, descartados = filtrar(resultados, config, ahora)
    hoy = ahora.astimezone(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M")
    if not elegidos:
        texto = (f"Sin alertas oficiales encontradas al {hoy}; no implica ausencia de riesgo. "
                 f"Descartados {descartados} resultados (otro dominio, sin fecha o de más de "
                 f"{config['antiguedad_maxima_horas']} h).")
    else:
        lineas = [f"[{i}] {r['fecha'].strftime('%d/%m %H:%M')} UTC · {r['dominio']} · {r['titulo']}: "
                  f"{r['resumen']} ({r['url']})" for i, r in enumerate(elegidos, 1)]
        texto = (f"Avisos oficiales al {hoy} (últimas {config['antiguedad_maxima_horas']} h):\n"
                 + "\n".join(lineas) + f"\nDescartados: {descartados}.")

    fuentes = [{"turn": runtime.context.turn, "title": r["titulo"], "url": r["url"]} for r in elegidos]
    reporte = {
        "elegidos": [{**r, "fecha": r["fecha"].isoformat()} for r in elegidos],
        "descartados": [{"url": r.get("url"), "fecha": r.get("published_date")}
                        for r in resultados if r.get("url") not in {e["url"] for e in elegidos}],
    }
    return respond(runtime, texto[:MAX_TEXTO], artifact=reporte, sources=fuentes)
