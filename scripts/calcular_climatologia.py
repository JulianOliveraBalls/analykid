"""Genera datos/climatologia/<rio>.json y registra la celda de GloFAS en datos/rios.json.

Uso:
    python scripts/calcular_climatologia.py            # todos los ríos
    python scripts/calcular_climatologia.py tunuyan    # uno solo

Descarga river_discharge diario 1991-2020 de la Flood API de Open-Meteo para el
punto de cada río y calcula la media por día del año con una ventana de ±15 días.
No marca el punto como verificado: eso se hace a mano después de revisar la celda.
"""
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
RIOS = RAIZ / "datos" / "rios.json"
SALIDA = RAIZ / "datos" / "climatologia"
URL = "https://flood-api.open-meteo.com/v1/flood"
INICIO, FIN = "1991-01-01", "2020-12-31"
VENTANA = 15


def descargar(lat: float, lon: float) -> dict:
    params = {"latitude": lat, "longitude": lon, "daily": "river_discharge",
              "start_date": INICIO, "end_date": FIN, "timezone": "GMT"}
    for espera in (2, 4, 8, None):
        try:
            r = requests.get(URL, params=params, timeout=60)
            if r.status_code == 200:
                return r.json()
            if r.status_code not in (429, 500, 502, 503, 504) or espera is None:
                r.raise_for_status()
        except requests.Timeout:
            if espera is None:
                raise
        time.sleep(espera)
    raise RuntimeError("sin respuesta de la Flood API")


def indice_dia(d: date) -> int:
    """0..365 con el 29/2 en el índice 59 (calendario de año bisiesto)."""
    return (date(2000, d.month, d.day) - date(2000, 1, 1)).days


def media_por_dia(fechas: list[str], valores: list) -> list:
    por_dia = [[] for _ in range(366)]
    for f, v in zip(fechas, valores):
        if v is not None:
            por_dia[indice_dia(date.fromisoformat(f))].append(v)
    medias = []
    for i in range(366):
        vecinos = [v for k in range(i - VENTANA, i + VENTANA + 1) for v in por_dia[k % 366]]
        medias.append(round(sum(vecinos) / len(vecinos), 2) if vecinos else None)
    return medias


def procesar(clave: str, rio: dict) -> dict:
    lat, lon = rio["consulta"]["latitud"], rio["consulta"]["longitud"]
    datos = descargar(lat, lon)
    fechas, valores = datos["daily"]["time"], datos["daily"]["river_discharge"]
    validos = [v for v in valores if v is not None]
    if not validos:
        raise RuntimeError(f"{clave}: la API no devolvió caudales para ese punto")
    clima = {
        "rio": clave,
        "fuente": "Open-Meteo Flood API (GloFAS v4), river_discharge diario",
        "punto": {"latitud": datos["latitude"], "longitud": datos["longitude"]},
        "periodo": f"{INICIO}/{FIN}",
        "ventana_dias": VENTANA,
        "dias_validos": len(validos),
        "media_anual_m3s": round(sum(validos) / len(validos), 1),
        "generado": date.today().isoformat(),
        "media_por_dia_del_anio": media_por_dia(fechas, valores),
    }
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / f"{clave}.json").write_text(json.dumps(clima, ensure_ascii=False, indent=1), encoding="utf-8")
    rio["celda_api"] = clima["punto"]
    ref = rio.get("caudal_medio_referencia_m3s")
    print(f"{clave}: celda {clima['punto']} · media 1991-2020 {clima['media_anual_m3s']} m³/s"
          + (f" (referencia de la estación: {ref} m³/s)" if ref else ""))
    return clima


def main() -> None:
    catalogo = json.loads(RIOS.read_text(encoding="utf-8"))
    pedidos = sys.argv[1:] or list(catalogo["rios"])
    for clave in pedidos:
        if clave not in catalogo["rios"]:
            print(f"ERROR: río desconocido '{clave}'. Opciones: {', '.join(catalogo['rios'])}")
            continue
        try:
            procesar(clave, catalogo["rios"][clave])
        except Exception as e:  # el script sigue con el resto de los ríos
            print(f"ERROR {clave}: {e}")
    RIOS.write_text(json.dumps(catalogo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Revisá cada celda en un mapa y completá 'verificado' en datos/rios.json.")


if __name__ == "__main__":
    main()
