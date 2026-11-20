"""web_search: alertas e información recientes, solo de dominios oficiales.

Busca con la API de Tavily limitada a datos/dominios_oficiales.json y, además,
descarta en código lo que no sea de esos dominios, no tenga fecha o tenga más
de 48 horas. El modelo solo indica la zona: la consulta la arma la tool.

- Si la zona no da resultados, repite la búsqueda a nivel provincial (Tavily
  es inestable con consultas por localidad) y lo aclara en el texto.
- Marca como ALERTA solo lo que menciona una alerta o aviso meteorológico; el
  resto (pronósticos, comunicados) es «información oficial»: contexto, no fija
  el nivel mínimo del semáforo.
"""
import os
import re
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
ZONA_PROVINCIAL = "Mendoza"
ALERTA = re.compile(
    r"\b(alerta|aviso)s?\s+(amarill|naranja|roj|por\b|de\s+(tormenta|lluvia|viento|granizo|crecida)"
    r"|a\s+(muy\s+)?corto\s+plazo)", re.IGNORECASE)


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


def es_alerta(texto: str) -> bool:
    """¿Menciona una alerta o aviso meteorológico (no un pronóstico o comunicado)?"""
    return bool(ALERTA.search(texto))


def filtrar(resultados: list[dict], config: dict, ahora: datetime) -> tuple[list[dict], int]:
    """Resultados válidos (los más recientes primero, hasta el máximo) y cantidad de descartados."""
    dominios = [d["dominio"] for d in config["dominios"]]
    limite = ahora - timedelta(hours=config["antiguedad_maxima_horas"])
    validos = []
    for r in resultados:
        dominio, fecha = dominio_oficial(r.get("url", ""), dominios), _fecha(r.get("published_date"))
        if dominio and fecha and limite <= fecha <= ahora + timedelta(hours=1):
            titulo, resumen = r.get("title", ""), " ".join(r.get("content", "").split())
            validos.append({"fecha": fecha, "dominio": dominio, "titulo": titulo,
                            "resumen": resumen[:MAX_RESUMEN], "url": r["url"],
                            "es_alerta": es_alerta(f"{titulo} {resumen}")})
    validos.sort(key=lambda r: r["fecha"], reverse=True)
    elegidos = validos[:config["max_resultados"]]
    return elegidos, len(resultados) - len(elegidos)


def _buscar(consulta: str, config: dict, clave: str) -> tuple[list | None, str | None]:
    datos, causa = pedir(URL, cuerpo={
        "query": consulta, "topic": "news", "time_range": "week", "max_results": CANDIDATOS,
        "include_domains": [d["dominio"] for d in config["dominios"]],
    }, headers={"Authorization": f"Bearer {clave}"})
    if causa:
        return None, causa
    return (datos.get("results", []) if isinstance(datos, dict) else []), None


def redactar(elegidos: list[dict], descartados: int, zona_usada: str, zona_pedida: str,
             horas: int, hoy: str) -> str:
    """Texto para el modelo: ALERTA o información oficial, y el alcance de la búsqueda."""
    alcance = "" if zona_usada == zona_pedida else (
        f" Sin resultados para «{zona_pedida}»: se buscó a nivel provincial ({zona_usada}).")
    if not elegidos:
        return (f"Sin alertas oficiales encontradas al {hoy}; no implica ausencia de riesgo. "
                f"Descartados {descartados} resultados (otro dominio, sin fecha o de más de {horas} h)."
                + alcance)
    lineas = [
        f"[{i}] {'ALERTA' if r['es_alerta'] else 'Información oficial'} · "
        f"{r['fecha'].strftime('%d/%m %H:%M')} UTC · {r['dominio']} · {r['titulo']}: "
        f"{r['resumen']} ({r['url']})"
        for i, r in enumerate(elegidos, 1)
    ]
    alertas = sum(r["es_alerta"] for r in elegidos)
    nota = (f"{alertas} alerta(s) oficial(es): fijan el nivel mínimo del semáforo." if alertas else
            "Ninguna es una alerta: es información oficial de contexto y no fija el nivel mínimo; "
            "en el informe va como «sin alertas oficiales vigentes».")
    return (f"Resultados oficiales al {hoy} (últimas {horas} h).{alcance}\n" + "\n".join(lineas)
            + f"\n{nota} Descartados: {descartados}.")


@tool
def web_search(zona: str, runtime: ToolRuntime[Context]) -> Command:
    """Busca alertas e información oficial (SMN, Gobierno de Mendoza, Irrigación, INA)
    de las últimas 48 horas para una zona de Mendoza. `zona` es el nombre de la
    localidad o del oasis (por ejemplo «Tupungato» o «Valle de Uco»). Solo los
    resultados marcados ALERTA son alertas; no encontrar alertas no significa que
    no haya riesgo.
    """
    config = cargar_json("dominios_oficiales.json")
    clave = os.getenv("TAVILY_API_KEY")
    if not clave:
        return respond(runtime, error(
            "web_search", "falta TAVILY_API_KEY",
            "Seguí sin alertas oficiales y aclaralo en el informe."))

    ahora = datetime.now(timezone.utc)
    zonas = [zona] if zona.strip().lower() == ZONA_PROVINCIAL.lower() else [zona, ZONA_PROVINCIAL]
    resultados, elegidos, zona_usada = [], [], zona
    for z in zonas:
        consulta = config["plantilla_consulta"].format(zona="" if z == ZONA_PROVINCIAL else z).strip()
        encontrados, causa = _buscar(consulta, config, clave)
        if causa:
            return respond(runtime, error(
                "web_search", f"Tavily: {causa}", "Seguí sin alertas oficiales y aclaralo en el informe."))
        resultados += encontrados
        elegidos, _ = filtrar(encontrados, config, ahora)
        zona_usada = z
        if elegidos:
            break
    descartados = len(resultados) - len(elegidos)

    hoy = ahora.astimezone(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M")
    texto = redactar(elegidos, descartados, zona_usada, zona, config["antiguedad_maxima_horas"], hoy)
    fuentes = [{"turn": runtime.context.turn, "title": r["titulo"], "url": r["url"]} for r in elegidos]
    urls_elegidas = {e["url"] for e in elegidos}
    reporte = {
        "zona_usada": zona_usada,
        "elegidos": [{**r, "fecha": r["fecha"].isoformat()} for r in elegidos],
        "descartados": [{"url": r.get("url"), "fecha": r.get("published_date")}
                        for r in resultados if r.get("url") not in urls_elegidas],
    }
    return respond(runtime, texto[:MAX_TEXTO], artifact=reporte, sources=fuentes)
