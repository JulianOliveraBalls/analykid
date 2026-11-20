"""Tests del corpus del RAG: frontmatter, citas y tamaño de los fragmentos (sin embeddings)."""
import json

from rag.ingest import CHUNK, cargar_corpus
from rag.store import DOCS_DIR, RAG_DIR

FRAGMENTOS = cargar_corpus()   # falla si un frontmatter es inválido o una cita no existe


def test_seis_documentos_indexables():
    assert len({f.metadata["source"] for f in FRAGMENTOS}) == len(list(DOCS_DIR.glob("*.md"))) == 6


def test_fragmentos_con_cita_y_sin_linea_fuente():
    for f in FRAGMENTOS:
        m = f.metadata
        assert m["seccion"] and m["fuente_id"] and m["organismo"] and m["url"].startswith("http")
        assert m["ambito"] in {"local", "internacional", "local e internacional"}
        assert "Fuente:" not in f.page_content


def test_fragmentos_no_superan_el_tamano():
    assert max(len(f.page_content) for f in FRAGMENTOS) <= CHUNK


def test_preguntas_de_evaluacion_apuntan_a_documentos_del_corpus():
    preguntas = json.loads((RAG_DIR / "preguntas_eval.json").read_text(encoding="utf-8"))["preguntas"]
    documentos = {f.metadata["source"] for f in FRAGMENTOS}
    assert len(preguntas) == 12 and {p["documento"] for p in preguntas} == documentos
