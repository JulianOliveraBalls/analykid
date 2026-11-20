"""Tests de la lógica de las tools de datos (sin red ni modelo)."""
import importlib
from datetime import datetime, timedelta, timezone

from tools import enso, river, weather
from tools.common import cargar_json

# `tools.web_search` es también el nombre de la tool que exporta el paquete.
web_search = importlib.import_module("tools.web_search")


# --- get_enso_status -----------------------------------------------------------

RONI = """SEAS   YR  ANOM
MAM  2026 -0.04
AMJ  2026  0.49
MJJ  2026  0.97
JJA  2026  1.36
JAS  2026  1.69
ASO  2026  1.97
"""


def test_enso_parsea_la_ultima_columna():
    filas = enso.parsear(RONI)
    assert filas[0] == ("MAM", 2026, -0.04) and filas[-1] == ("ASO", 2026, 1.97)


def test_enso_parsea_formato_oni_con_columna_total():
    assert enso.parsear(" SEAS  YR   TOTAL   ANOM\n  DJF 1950  25.01  -1.32\n") == [("DJF", 1950, -1.32)]


def test_enso_clasificacion():
    assert [enso.categoria(v) for v in (0.3, 0.7, 1.2, 1.97, 2.1, -1.6)] == [
        "sin evento", "débil", "moderado", "fuerte", "muy fuerte", "fuerte"]
    assert (enso.fase(0.5), enso.fase(-0.5), enso.fase(0.49)) == ("El Niño", "La Niña", "Neutral")


def test_enso_resumen_episodio_y_tendencia():
    r = enso.resumir(enso.parsear(RONI), trimestres=2)
    assert r["fase"] == "El Niño" and r["tendencia"] == "sube"
    assert r["trimestres_consecutivos"] == 4 and r["episodio"] is False
    assert [s["trimestre"] for s in r["serie"]] == ["JAS 2026", "ASO 2026"]


def test_enso_neutral_no_cuenta_trimestres():
    assert enso.trimestres_consecutivos([0.8, 0.2]) == 0


# --- get_weather_forecast ------------------------------------------------------

def test_resolver_localidad_por_clave_nombre_y_tildes():
    assert weather.resolver_localidad("tupungato") == ("tupungato", [])
    assert weather.resolver_localidad("San Rafael") == ("san_rafael", [])
    assert weather.resolver_localidad("Luján de Cuyo") == ("lujan_de_cuyo", [])


def test_resolver_localidad_inexistente_sugiere_parecidas():
    clave, parecidas = weather.resolver_localidad("san rafel")
    assert clave is None and parecidas[0] == "san_rafael" and len(parecidas) <= 3


def test_parametros_incluyen_lo_que_usan_los_indicadores():
    assert {"precipitation_sum", "precipitation_probability_max", "cape_max",
            "wind_gusts_10m_max", "temperature_2m_min"} <= set(weather.parametros_diarios())


def test_indicadores_del_pronostico():
    daily = {
        "time": ["2026-11-20", "2026-11-21", "2026-11-22"],
        "precipitation_sum": [12.34, 0.0, 25.0],
        "precipitation_probability_max": [80, 10, 65],
        "cape_max": [500.0, 2300.0, 900.0],
        "wind_gusts_10m_max": [30.4, 55.6, 20.0],
        "temperature_2m_max": [25.0, 30.0, 22.0],
        "temperature_2m_min": [11.0, 14.0, 8.5],
    }
    dias, ind = weather.calcular_indicadores(daily)
    assert ind["lluvia_acumulada_mm"] == 37.3 and ind["lluvia_max_mm"] == 25.0
    assert ind["cape_max_jkg"] == 2300 and ind["fecha_cape_max"] == "2026-11-21"
    assert ind["prob_dia_cape_max_pct"] == 10
    assert ind["rafaga_max_kmh"] == 56 and ind["tmin_mas_baja_c"] == 8.5
    assert ind["dias_lluvia_10mm"] == 2
    assert ind["dias_favorables_hongos"] == 1     # el 22/11 tiene mínima < 10 °C
    assert dias[0]["lluvia_mm"] == 12.3


def test_indicadores_toleran_valores_nulos():
    daily = {k: [None] for k in ("precipitation_sum", "precipitation_probability_max", "cape_max",
                                 "wind_gusts_10m_max", "temperature_2m_max", "temperature_2m_min")}
    _, ind = weather.calcular_indicadores({"time": ["2026-11-20"], **daily})
    assert ind["lluvia_max_mm"] is None and ind["dias_favorables_hongos"] == 0


# --- get_river_discharge -------------------------------------------------------

def test_caudal_cociente_y_tendencia():
    medias = [10.0] * 366
    r = river.calcular(["2026-11-20", "2026-11-21", "2026-11-22"], [12.0, 31.0, 20.0], medias)
    assert r["caudal_max_m3s"] == 31 and r["fecha_max"] == "2026-11-21"
    assert r["media_1991_2020_m3s"] == 10 and r["cociente"] == 3.1
    assert r["tendencia"] == "sube"


def test_caudal_usa_la_media_de_cada_dia_del_anio():
    medias = [None] * 366
    medias[59], medias[60] = 4.0, 8.0          # 29/2 y 1/3 en calendario bisiesto
    assert river.media_historica(medias, ["2028-02-29", "2027-03-01"]) == 6.0


def test_caudal_sin_datos_devuelve_none():
    assert river.calcular(["2026-11-20"], [None], [10.0] * 366) is None


# --- web_search ----------------------------------------------------------------

CONFIG = {"dominios": [{"dominio": "smn.gob.ar"}, {"dominio": "mendoza.gov.ar"}],
          "antiguedad_maxima_horas": 48, "max_resultados": 3}
AHORA = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)


def _r(url, horas=None, **extra):
    fecha = None if horas is None else (AHORA - timedelta(hours=horas)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    return {"url": url, "published_date": fecha, "title": "t", "content": "c", **extra}


def test_alertas_filtra_dominio_fecha_y_antiguedad():
    resultados = [
        _r("https://www.smn.gob.ar/alertas", horas=2),
        _r("https://prensa.mendoza.gov.ar/aviso", horas=30),
        _r("https://diario.com.ar/smn.gob.ar", horas=1),       # otro dominio
        _r("https://smn.gob.ar/viejo", horas=60),              # más de 48 h
        _r("https://smn.gob.ar/sin-fecha"),                    # sin fecha
    ]
    elegidos, descartados = web_search.filtrar(resultados, CONFIG, AHORA)
    assert [e["url"] for e in elegidos] == ["https://www.smn.gob.ar/alertas",
                                            "https://prensa.mendoza.gov.ar/aviso"]
    assert descartados == 3


def test_alertas_respeta_el_maximo_y_ordena_por_fecha():
    resultados = [_r(f"https://smn.gob.ar/{h}", horas=h) for h in (10, 1, 5, 3)]
    elegidos, descartados = web_search.filtrar(resultados, CONFIG, AHORA)
    assert [e["url"] for e in elegidos] == ["https://smn.gob.ar/1", "https://smn.gob.ar/3",
                                            "https://smn.gob.ar/5"]
    assert descartados == 1


def test_alertas_acepta_fecha_iso():
    r = {"url": "https://smn.gob.ar/a", "published_date": "2026-11-20T12:00:00Z"}
    assert len(web_search.filtrar([r], CONFIG, AHORA)[0]) == 1


def test_dominio_oficial_no_acepta_sufijos_falsos():
    assert web_search.dominio_oficial("https://falsosmn.gob.ar/x", ["smn.gob.ar"]) is None
    assert web_search.dominio_oficial("https://ws.smn.gob.ar/x", ["smn.gob.ar"]) == "smn.gob.ar"


def test_es_alerta_distingue_alertas_de_pronosticos():
    assert web_search.es_alerta("SMN: alerta amarilla por tormentas para el Valle de Uco")
    assert web_search.es_alerta("Aviso a muy corto plazo por tormentas fuertes")
    assert web_search.es_alerta("Rige alerta por viento Zonda")
    assert not web_search.es_alerta("Pronóstico Diario - Contingencias Mendoza: tormentas en el sur")
    assert not web_search.es_alerta("Defensa Civil recomienda tomar recaudos ante las precipitaciones")


def test_redactar_marca_alertas_y_respaldo_provincial():
    fecha = AHORA - timedelta(hours=1)
    info = {"fecha": fecha, "dominio": "mendoza.gov.ar", "titulo": "Pronóstico", "resumen": "r",
            "url": "https://x", "es_alerta": False}
    texto = web_search.redactar([info], 0, "Mendoza", "Tupungato", 48, "20/11/2026 12:00")
    assert "Información oficial" in texto and "ALERTA" not in texto.split("\n")[1]
    assert "nivel provincial" in texto and "no fija el nivel mínimo" in texto
    alerta = {**info, "es_alerta": True}
    texto = web_search.redactar([alerta], 2, "Tupungato", "Tupungato", 48, "20/11/2026 12:00")
    assert "[1] ALERTA" in texto and "fijan el nivel mínimo" in texto and "provincial" not in texto


def test_redactar_sin_resultados():
    texto = web_search.redactar([], 3, "Mendoza", "Tupungato", 48, "20/11/2026 12:00")
    assert texto.startswith("Sin alertas oficiales encontradas al 20/11/2026 12:00; no implica ausencia de riesgo")


def test_contactos_para_el_modelo() -> None:
    locs = cargar_json("localidades.json")["localidades"]
    tupungato = weather._contactos(locs["tupungato"]["emergencias"])
    assert "Defensa Civil municipal 2622 574912" in tupungato
    assert "Contingencias Climáticas, delegación Valle de Uco (Tunuyán), 02622 423036" in tupungato
    assert "sin contacto municipal verificado" in weather._contactos(locs["maipu"]["emergencias"])
