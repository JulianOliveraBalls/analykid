"""Semáforo por amenaza calculado en código, para las tarjetas de la UI.

Aplica la misma tabla y las mismas reglas que el system prompt (agente.py) a
los indicadores que devolvieron las tools. No es una tool: el modelo evalúa por
su cuenta para el informe, y la UI muestra este cálculo determinista para que el
resultado se vea de un vistazo y se pueda contrastar con el PDF.
"""
NIVELES = ["verde", "amarillo", "naranja", "rojo"]
SIN_DATOS = "sin datos"
NO_APLICA = "no aplica"

UMBRALES = {   # amarillo, naranja, rojo
    "pluvial": (10, 25, 50),
    "granizo": (1000, 2000, 3000),
    "crecida": (1.5, 2.0, 3.0),
    "sanitaria": (1, 2, 3),
}
ALUVIONAL = ((10, 1000), (20, 1500), (35, 2000))   # (lluvia mm, CAPE J/kg) por nivel
PROB_SUBE_GRANIZO = 60


def _nivel(valor, umbrales) -> int:
    """0 = verde … 3 = rojo."""
    return sum(valor >= u for u in umbrales)


def _amenaza(nombre: str, nivel: str, motivo: str) -> dict:
    return {"amenaza": nombre, "nivel": nivel, "motivo": motivo}


def _fecha(iso: str | None) -> str:
    return f"{iso[8:10]}/{iso[5:7]}" if iso else "s/d"


def evaluar(pronostico: dict | None, caudal: dict | None, perfil: str | None = None) -> list[dict]:
    """Cinco amenazas con nivel y motivo. `pronostico` y `caudal` son los artifacts
    de get_weather_forecast y get_river_discharge (None si la tool falló o no se llamó)."""
    resultado = []
    if pronostico is None:
        for nombre in ("Pluvial", "Granizo / tormenta", "Aluvional"):
            resultado.append(_amenaza(nombre, SIN_DATOS, "Sin pronóstico"))
    else:
        i = pronostico["indicadores"]
        lluvia, cape = i["lluvia_max_mm"] or 0, i["cape_max_jkg"] or 0

        n = _nivel(lluvia, UMBRALES["pluvial"])
        resultado.append(_amenaza("Pluvial", NIVELES[n],
                                  f"Lluvia máx. {lluvia} mm el {_fecha(i['fecha_lluvia_max'])}"))

        n = _nivel(cape, UMBRALES["granizo"])
        motivo = f"CAPE máx. {cape} J/kg el {_fecha(i['fecha_cape_max'])}"
        if n and (i["prob_dia_cape_max_pct"] or 0) >= PROB_SUBE_GRANIZO:
            n = min(n + 1, 3)
            motivo += f" con prob. {i['prob_dia_cape_max_pct']} % (sube un nivel)"
        resultado.append(_amenaza("Granizo / tormenta", NIVELES[n], motivo))

        n = sum(lluvia >= ll and cape >= c for ll, c in ALUVIONAL)
        motivo = f"Lluvia {lluvia} mm y CAPE {cape} J/kg"
        if not pronostico.get("piedemonte") and n > 1:
            n, motivo = 1, motivo + " (fuera del piedemonte: máximo amarillo)"
        resultado.append(_amenaza("Aluvional", NIVELES[n], motivo))

    if caudal is None:
        resultado.append(_amenaza("Crecida", SIN_DATOS, "Sin caudal"))
    else:
        n = _nivel(caudal["cociente"], UMBRALES["crecida"])
        resultado.append(_amenaza("Crecida", NIVELES[n],
                                  f"Caudal {caudal['cociente']} veces la media 1991-2020"))

    if perfil == "urbano":
        resultado.append(_amenaza("Sanitaria", NO_APLICA, "No aplica al perfil urbano"))
    elif pronostico is None:
        resultado.append(_amenaza("Sanitaria", SIN_DATOS, "Sin pronóstico"))
    else:
        dias = pronostico["indicadores"]["dias_favorables_hongos"]
        resultado.append(_amenaza("Sanitaria", NIVELES[_nivel(dias, UMBRALES["sanitaria"])],
                                  f"{dias} día(s) favorables a hongos (regla 10:10:24)"))
    return resultado


def nivel_maximo(amenazas: list[dict]) -> str:
    niveles = [NIVELES.index(a["nivel"]) for a in amenazas if a["nivel"] in NIVELES]
    return NIVELES[max(niveles)] if niveles else SIN_DATOS
