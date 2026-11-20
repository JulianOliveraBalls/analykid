"""Evaluación del RAG: acierto@4 y posición media sobre rag/preguntas_eval.json.

Requiere la base ya indexada (python -m rag.ingest) y GOOGLE_API_KEY.
Ejecutar:   python -m rag.evaluar
"""
import json

from rag.store import DB_DIR, RAG_DIR, get_store

K = 4        # el mismo k que usa search_knowledge_base
META = 10    # aciertos mínimos sobre 12


def main() -> None:
    if not DB_DIR.exists():
        raise SystemExit("Falta la base vectorial. Ejecutá: python -m rag.ingest")
    preguntas = json.loads((RAG_DIR / "preguntas_eval.json").read_text(encoding="utf-8"))["preguntas"]
    store = get_store()
    posiciones = []
    for p in preguntas:
        fuentes = [c.metadata["source"] for c in store.similarity_search(p["pregunta"], k=K)]
        pos = fuentes.index(p["documento"]) + 1 if p["documento"] in fuentes else None
        posiciones.append(pos)
        print(f"{'✔' if pos else '✘'} {pos or '-'}  {p['pregunta']}  →  {fuentes[0]}")
    aciertos = [x for x in posiciones if x]
    media = sum(aciertos) / len(aciertos) if aciertos else 0
    print(f"\nAcierto@{K}: {len(aciertos)}/{len(preguntas)} (meta ≥ {META}) · posición media {media:.2f}")


if __name__ == "__main__":
    main()
