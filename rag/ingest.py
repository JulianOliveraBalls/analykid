"""Ingesta del RAG: documentos -> fragmentos con cita -> embeddings -> Chroma.

Se ejecuta una vez (y de nuevo cada vez que cambien los documentos), desde la
carpeta del proyecto:   python -m rag.ingest

Cada documento tiene frontmatter YAML (titulo, amenaza, perfiles, fuentes) y
secciones `##` cerradas por una o más líneas `Fuente: <id>[, <id>]`. Cada
sección es un fragmento (o varios si supera CHUNK) con la metadata de sus
fuentes; las líneas `Fuente:` se quitan del texto.
"""
import re
import time
from pathlib import Path

import yaml
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from rag.store import DB_DIR, DOCS_DIR, get_store

CHUNK, OVERLAP = 900, 120
LOTE, PAUSA_S = 20, 2          # embeddings por lote y pausa entre lotes (límite gratuito)
FUENTE = re.compile(r"^Fuente:\s*(.+)$", re.MULTILINE)


def _lista(valor) -> list[str]:
    return valor if isinstance(valor, list) else [valor]


def leer(ruta: Path) -> tuple[dict, str]:
    """Separa el frontmatter YAML del cuerpo markdown."""
    _, frontmatter, cuerpo = ruta.read_text(encoding="utf-8").split("---", 2)
    return yaml.safe_load(frontmatter), cuerpo


def fragmentar(nombre: str, meta: dict, cuerpo: str) -> list[Document]:
    """Fragmentos de un documento, cada uno con su sección y sus fuentes."""
    fuentes = {f["id"]: f for f in meta["fuentes"]}
    base = {"source": nombre, "titulo": meta["titulo"],
            "amenaza": ", ".join(_lista(meta["amenaza"])), "perfiles": ", ".join(_lista(meta["perfiles"]))}
    secciones = MarkdownHeaderTextSplitter([("##", "seccion")]).split_text(cuerpo)
    divisor = RecursiveCharacterTextSplitter(chunk_size=CHUNK, chunk_overlap=OVERLAP)

    fragmentos = []
    for s in secciones:
        if "seccion" not in s.metadata:          # introducción antes del primer ##
            continue
        ids = list(dict.fromkeys(i.strip() for linea in FUENTE.findall(s.page_content)
                                 for i in linea.split(",")))
        desconocidos = [i for i in ids if i not in fuentes]
        if not ids or desconocidos:
            raise ValueError(f"{nombre} «{s.metadata['seccion']}»: fuente ausente o desconocida {desconocidos}")
        citadas = [fuentes[i] for i in ids]
        ambitos = {f["ambito"] for f in citadas}
        meta_seccion = {
            **base, "seccion": s.metadata["seccion"],
            "fuente_id": ", ".join(ids),
            "organismo": "; ".join(f["organismo"] for f in citadas),
            "ambito": "local e internacional" if len(ambitos) > 1 else ambitos.pop(),
            "anio": ", ".join(str(f["anio"]) for f in citadas),
            "url": citadas[0]["url"],
        }
        texto = re.sub(r"\n{3,}", "\n\n", FUENTE.sub("", s.page_content)).strip()
        for parte in divisor.split_text(texto):
            fragmentos.append(Document(page_content=parte, metadata=meta_seccion))
    return fragmentos


def cargar_corpus() -> list[Document]:
    archivos = sorted(DOCS_DIR.glob("*.md"))
    if not archivos:
        raise SystemExit(f"No hay documentos .md en {DOCS_DIR}")
    return [f for p in archivos for f in fragmentar(p.name, *leer(p))]


def main() -> None:
    fragmentos = cargar_corpus()
    store = get_store()
    store.reset_collection()           # se reinicia para no duplicar
    for i in range(0, len(fragmentos), LOTE):
        if i:
            time.sleep(PAUSA_S)
        store.add_documents(fragmentos[i:i + LOTE])
    documentos = len({f.metadata["source"] for f in fragmentos})
    print(f"{documentos} documentos -> {len(fragmentos)} fragmentos indexados en {DB_DIR}")


if __name__ == "__main__":
    main()
