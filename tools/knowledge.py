"""Conocimiento propio: búsqueda en el RAG y carga de skills."""
from functools import cache

from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from tools.common import BASE_DIR, Context, error, respond

SKILLS_DIR = BASE_DIR / "skills"
K = 4                  # fragmentos por consulta (4 × ≤ 900 caracteres)
MAX_SKILL = 6000       # caracteres máximos de una skill


@cache
def _store():
    """Base vectorial, abierta la primera vez que se usa (no al importar)."""
    from rag.store import DB_DIR, get_store

    if not DB_DIR.exists():
        raise FileNotFoundError("falta la base vectorial")
    return get_store()


def _descripcion(nombre: str) -> str:
    """Valor de `description:` en el encabezado de una skill."""
    for linea in (SKILLS_DIR / f"{nombre}.md").read_text(encoding="utf-8").splitlines():
        if linea.startswith("description:"):
            return linea.removeprefix("description:").strip()
    return ""


def _skills() -> list[str]:
    return sorted(p.stem for p in SKILLS_DIR.glob("*.md"))


def listar_skills() -> str:
    """'nombre: descripción' de cada skill, para el system prompt."""
    return "; ".join(f"{n}: {_descripcion(n)}" for n in _skills())


@tool
def search_knowledge_base(consulta: str, runtime: ToolRuntime[Context]) -> Command:
    """Busca recomendaciones en la base de conocimiento propia (guías de organismos
    oficiales sobre aluviones, inundación en fincas, tormentas eléctricas, granizo
    y peronóspora en vid, y la temporada El Niño 2026-2027 en Mendoza).

    Devuelve 4 fragmentos con documento, sección, organismo y ámbito. Citá cada
    medida que tomes de acá como [Documento — Sección].
    """
    try:
        chunks = _store().similarity_search(consulta, k=K)
    except FileNotFoundError:
        return respond(runtime, error(
            "search_knowledge_base", "falta la base vectorial",
            "Seguí sin el corpus y aclará en el informe que las medidas no tienen cita."))
    except Exception as e:  # embeddings: 429, red, clave inválida
        return respond(runtime, error(
            "search_knowledge_base", f"no se pudo consultar ({type(e).__name__})",
            "Reintentá una vez; si vuelve a fallar, seguí sin el corpus y aclaralo."))

    if not chunks:
        return respond(runtime, "Sin resultados en la base de conocimiento.")

    bloques, fuentes, reporte = [], [], []
    for i, c in enumerate(chunks, 1):
        m = c.metadata
        documento, seccion = m.get("titulo", m["source"]), m.get("seccion", "")
        origen = ", ".join(x for x in (m.get("organismo"), m.get("ambito")) if x)
        bloques.append(f"[{i}] {documento} — {seccion} ({origen})\n{c.page_content}")
        fuentes.append({
            "turn": runtime.context.turn,
            "title": f"{documento} — {seccion}",
            "url": m.get("url") or f"rag/docs/{m['source']}",
        })
        reporte.append({"documento": documento, "seccion": seccion, "origen": origen,
                        "fragmento": c.page_content[:150].replace("\n", " ")})
    return respond(runtime, "\n\n".join(bloques), artifact=reporte, sources=fuentes)


@tool
def load_skill(nombre: str) -> str:
    """Carga las instrucciones detalladas de una skill (las disponibles están en el
    system prompt). Cargá cada skill una sola vez por conversación: si ya está en
    el historial, no la vuelvas a pedir.
    """
    if nombre not in _skills():
        return error("load_skill", f"no existe la skill «{nombre}»",
                     f"Disponibles: {', '.join(_skills())}.")
    return (SKILLS_DIR / f"{nombre}.md").read_text(encoding="utf-8")[:MAX_SKILL]
