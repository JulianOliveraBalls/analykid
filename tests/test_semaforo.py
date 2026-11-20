"""Tests del semáforo calculado en código (mismas reglas que el system prompt)."""
from semaforo import evaluar, nivel_maximo


def _pronostico(lluvia=0, cape=0, prob=0, hongos=0, piedemonte=True):
    return {"piedemonte": piedemonte, "indicadores": {
        "lluvia_max_mm": lluvia, "fecha_lluvia_max": "2026-11-24", "cape_max_jkg": cape,
        "fecha_cape_max": "2026-11-26", "prob_dia_cape_max_pct": prob, "dias_favorables_hongos": hongos}}


def _niveles(*args, **kw):
    return {a["amenaza"]: a["nivel"] for a in evaluar(*args, **kw)}


def test_todo_verde():
    n = _niveles(_pronostico(), {"cociente": 1.0})
    assert set(n.values()) == {"verde"}


def test_umbrales_por_amenaza():
    n = _niveles(_pronostico(lluvia=25, cape=2300, prob=10, hongos=3), {"cociente": 3.1})
    assert n["Pluvial"] == "naranja" and n["Granizo / tormenta"] == "naranja"
    assert n["Aluvional"] == "naranja"      # 25 mm y 2300 J/kg: ≥ 20 y ≥ 1500
    assert n["Crecida"] == "rojo" and n["Sanitaria"] == "rojo"


def test_granizo_sube_un_nivel_con_probabilidad_alta():
    assert _niveles(_pronostico(cape=1200, prob=60), None)["Granizo / tormenta"] == "naranja"
    assert _niveles(_pronostico(cape=3500, prob=90), None)["Granizo / tormenta"] == "rojo"
    assert _niveles(_pronostico(cape=500, prob=90), None)["Granizo / tormenta"] == "verde"


def test_aluvional_fuera_del_piedemonte_maximo_amarillo():
    assert _niveles(_pronostico(lluvia=40, cape=2500, piedemonte=False), None)["Aluvional"] == "amarillo"


def test_sin_datos_nunca_es_verde():
    n = _niveles(None, None)
    assert set(n.values()) == {"sin datos"} and nivel_maximo(evaluar(None, None)) == "sin datos"


def test_sanitaria_no_aplica_a_urbano():
    assert _niveles(_pronostico(hongos=3), None, perfil="urbano")["Sanitaria"] == "no aplica"


def test_nivel_maximo():
    assert nivel_maximo(evaluar(_pronostico(lluvia=12), {"cociente": 2.0})) == "naranja"
