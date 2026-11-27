"""get_weather_forecast: pronóstico diario de Open-Meteo e indicadores de riesgo.

El modelo solo pasa la localidad (clave o nombre del catálogo) y los días: las
coordenadas salen de datos/localidades.json y las variables de
datos/variables.json. Todos los indicadores se calculan acá, nunca el modelo.
"""
import difflib
import unicodedata
from datetime import date

from langchain.tools import ToolRuntime, tool
from langgraph.types import Command
from pydantic import Field
from typing_extensions import Annotated

from tools.common import Context, cargar_json, error, pedir, respond

URL = "https://api.open-meteo.com/v1/forecast"
ZONA = "America/Argentina/Mendoza"
OASIS = {"norte": "Norte", "este": "Este", "valle_de_uco": "Valle de Uco",
         "sur": "Sur", "alta_montana": "Alta montaña"}
LLUVIA_INTENSA_MM = 10     # días ≥ 10 mm
HONGOS_MIN_C = 10          # regla 10:10:24 de la peronóspora: ≥ 10 mm y mínima ≥ 10 °C


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "_".join(sin_tildes.lower().replace("-", " ").replace("(", " ").replace(")", " ").split())


def resolver_localidad(texto: str) -> tuple[str | None, list[str]]:
    """Clave del catálogo para `texto` (clave o nombre). Si no existe: (None, 3 parecidas)."""
    localidades = cargar_json("localidades.json")["localidades"]
    buscado = _normalizar(texto)
    for clave, l in localidades.items():
        if buscado in (clave, _normalizar(l["nombre"]), _normalizar(l["departamento"])):
            return clave, []
    return None, difflib.get_close_matches(buscado, list(localidades), n=3, cutoff=0.4)


def parametros_diarios() -> list[str]:
    """Todos los parámetros de todos los grupos de variables.json."""
    grupos = cargar_json("variables.json")["variables"].values()
    return [p for g in grupos for p in g["parametros"]]


def _fecha(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m")


def _maximo(dias: list[dict], campo: str) -> tuple[float | None, str | None]:
    validos = [d for d in dias if d[campo] is not None]
    if not validos:
        return None, None
    d = max(validos, key=lambda d: d[campo])
    return d[campo], d["fecha"]


def calcular_indicadores(daily: dict) -> tuple[list[dict], dict]:
    """Filas por día e indicadores, a partir del bloque `daily` de Open-Meteo."""
    dias = [
        {
            "fecha": daily["time"][i],
            "lluvia_mm": daily["precipitation_sum"][i],
            "prob_pct": daily["precipitation_probability_max"][i],
            "cape_jkg": daily["cape_max"][i],
            "rafaga_kmh": daily["wind_gusts_10m_max"][i],
            "tmax_c": daily["temperature_2m_max"][i],
            "tmin_c": daily["temperature_2m_min"][i],
        }
        for i in range(len(daily["time"]))
    ]
    lluvia_max, f_lluvia = _maximo(dias, "lluvia_mm")
    prob_max, f_prob = _maximo(dias, "prob_pct")
    cape_max, f_cape = _maximo(dias, "cape_jkg")
    rafaga_max, f_rafaga = _maximo(dias, "rafaga_kmh")
    minimas = [d for d in dias if d["tmin_c"] is not None]
    dia_frio = min(minimas, key=lambda d: d["tmin_c"]) if minimas else None
    prob_dia_cape = next((d["prob_pct"] for d in dias if d["fecha"] == f_cape), None)

    def lluvia(d):
        return d["lluvia_mm"] or 0

    indicadores = {
        "lluvia_acumulada_mm": round(sum(lluvia(d) for d in dias), 1),
        "lluvia_max_mm": lluvia_max, "fecha_lluvia_max": f_lluvia,
        "prob_max_pct": prob_max, "fecha_prob_max": f_prob,
        "cape_max_jkg": cape_max, "fecha_cape_max": f_cape,
        "prob_dia_cape_max_pct": prob_dia_cape,
        "rafaga_max_kmh": rafaga_max, "fecha_rafaga_max": f_rafaga,
        "tmin_mas_baja_c": dia_frio["tmin_c"] if dia_frio else None,
        "fecha_tmin_mas_baja": dia_frio["fecha"] if dia_frio else None,
        "dias_lluvia_10mm": sum(lluvia(d) >= LLUVIA_INTENSA_MM for d in dias),
        "dias_favorables_hongos": sum(
            lluvia(d) >= LLUVIA_INTENSA_MM and (d["tmin_c"] or -99) >= HONGOS_MIN_C for d in dias
        ),
    }
    return dias, _redondear(dias, indicadores)


def _redondear(dias: list[dict], ind: dict) -> dict:
    """1 decimal para mm y °C; enteros para %, km/h y J/kg."""
    enteros = ("prob", "cape", "rafaga")
    for fila in (*dias, ind):
        for k, v in fila.items():
            if isinstance(v, float):
                fila[k] = round(v) if k.startswith(enteros) else round(v, 1)
    return ind


def _contactos(e: dict) -> str:
    municipal = e.get("defensa_civil_municipal")
    if municipal and e.get("verificado"):
        texto = f"emergencias {e['general']}; Defensa Civil municipal {municipal}"
    else:
        texto = f"emergencias {e['general']} (sin contacto municipal verificado)"
    cc = e["contingencias_climaticas"]
    return f"{texto}; denuncia de daños agrícolas: Contingencias Climáticas, {cc['delegacion']}, {cc['telefono']}"


def texto_para_modelo(clave: str, loc: dict, dias: list[dict], ind: dict) -> str:
    def f(iso):
        return _fecha(iso) if iso else "s/d"

    cabecera = (
        f"Pronóstico {loc['nombre']} ({clave}) · depto {loc['departamento']} · oasis "
        f"{OASIS.get(loc['oasis'], loc['oasis'])} · piedemonte {'sí' if loc['piedemonte'] else 'no'}"
        f" · río {loc['rio']} · {_contactos(loc['emergencias'])}"
    )
    tabla = ["fecha | lluvia mm | prob % | CAPE J/kg | ráfaga km/h | mín/máx °C"] + [
        f"{_fecha(d['fecha'])} | {d['lluvia_mm']} | {d['prob_pct']} | {d['cape_jkg']} | "
        f"{d['rafaga_kmh']} | {d['tmin_c']}/{d['tmax_c']}"
        for d in dias
    ]
    resumen = (
        f"Indicadores: lluvia acumulada {ind['lluvia_acumulada_mm']} mm; lluvia máx "
        f"{ind['lluvia_max_mm']} mm el {f(ind['fecha_lluvia_max'])}; prob máx "
        f"{ind['prob_max_pct']} % el {f(ind['fecha_prob_max'])}; CAPE máx {ind['cape_max_jkg']} "
        f"J/kg el {f(ind['fecha_cape_max'])} (prob ese día {ind['prob_dia_cape_max_pct']} %); "
        f"ráfaga máx {ind['rafaga_max_kmh']} km/h el {f(ind['fecha_rafaga_max'])}; mínima más baja "
        f"{ind['tmin_mas_baja_c']} °C el {f(ind['fecha_tmin_mas_baja'])}; días ≥ 10 mm "
        f"{ind['dias_lluvia_10mm']}; días favorables a hongos {ind['dias_favorables_hongos']}."
    )
    return "\n".join([cabecera, *tabla, resumen])


@tool
def get_weather_forecast(
    localidad: str,
    runtime: ToolRuntime[Context],
    dias: Annotated[int, Field(ge=1, le=16)] = 7,
) -> Command:
    """Pronóstico diario de una localidad de Mendoza con los indicadores de riesgo ya
    calculados (lluvia máxima y acumulada, probabilidad, CAPE, ráfagas, mínima, días
    ≥ 10 mm y días favorables a hongos), más departamento, oasis, piedemonte, río y
    contactos de emergencia. `localidad` es la clave o el nombre del catálogo (por
    ejemplo «tupungato» o «San Rafael»); nunca coordenadas. `dias` va de 1 a 16
    y cuenta desde hoy: `dias=1` es solo hoy; para incluir mañana hacen falta 2.
    """
    clave, parecidas = resolver_localidad(localidad)
    if clave is None:
        return respond(runtime, error(
            "get_weather_forecast", f"la localidad «{localidad}» no está en el catálogo",
            f"Probá con: {', '.join(parecidas) or 'otra localidad de Mendoza'}, o preguntale al usuario."))

    loc = cargar_json("localidades.json")["localidades"][clave]
    datos, causa = pedir(URL, {
        "latitude": loc["latitud"], "longitude": loc["longitud"],
        "daily": ",".join(parametros_diarios()), "timezone": ZONA, "forecast_days": dias,
    })
    if causa:
        return respond(runtime, error(
            "get_weather_forecast", f"Open-Meteo: {causa}",
            "Seguí sin pronóstico: las amenazas que dependen de él van como «sin datos»."))
    try:
        filas, indicadores = calcular_indicadores(datos["daily"])
    except (KeyError, TypeError, IndexError) as e:
        return respond(runtime, error(
            "get_weather_forecast", f"respuesta inesperada de Open-Meteo ({e})",
            "Seguí sin pronóstico: las amenazas que dependen de él van como «sin datos»."))

    fuente = {"turn": runtime.context.turn, "title": f"Open-Meteo: pronóstico {loc['nombre']}",
              "url": "https://open-meteo.com/en/docs"}
    return respond(
        runtime, texto_para_modelo(clave, loc, filas, indicadores),
        artifact={"localidad": clave, "nombre": loc["nombre"], "departamento": loc["departamento"],
                  "oasis": OASIS.get(loc["oasis"], loc["oasis"]), "oasis_clave": loc["oasis"],
                  "piedemonte": loc["piedemonte"],
                  "rio": loc["rio"], "latitud": loc["latitud"], "longitud": loc["longitud"],
                  "dias": filas, "indicadores": indicadores, "emergencias": loc["emergencias"]},
        sources=[fuente],
    )
