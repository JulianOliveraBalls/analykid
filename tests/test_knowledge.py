"""Tests de tools/knowledge.py (sin red)."""
import time
from concurrent.futures import ThreadPoolExecutor

import rag.store
from tools import knowledge


def test_el_store_se_crea_una_sola_vez_con_consultas_en_paralelo(monkeypatch, tmp_path):
    creados = []

    def get_store_lento():
        time.sleep(0.05)              # ventana para que los hilos se pisen si no hay lock
        creados.append(object())
        return creados[-1]

    monkeypatch.setattr(rag.store, "get_store", get_store_lento)
    monkeypatch.setattr(rag.store, "DB_DIR", tmp_path)
    knowledge._abrir_store.cache_clear()
    with ThreadPoolExecutor(6) as ex:
        stores = list(ex.map(lambda _: knowledge._store(), range(6)))
    knowledge._abrir_store.cache_clear()
    assert len(creados) == 1 and all(s is creados[0] for s in stores)
