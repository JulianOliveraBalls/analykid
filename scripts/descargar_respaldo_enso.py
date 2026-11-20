"""Descarga el índice RONI de NOAA a datos/respaldo/ (versionado), el que usa get_enso_status.

Uso:
    python scripts/descargar_respaldo_enso.py
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "datos" / "respaldo"
ARCHIVOS = {
    "RONI.ascii.txt": "https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt",
}


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    registro_path = DESTINO / "descarga.json"
    registro = json.loads(registro_path.read_text(encoding="utf-8")) if registro_path.exists() else {}
    for nombre, url in ARCHIVOS.items():
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            if not r.text.lstrip().startswith("SEAS"):
                raise ValueError("formato inesperado (no empieza con la cabecera SEAS)")
            (DESTINO / nombre).write_text(r.text, encoding="utf-8")
            registro[nombre] = {"url": url, "descargado": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            ultima = r.text.strip().splitlines()[-1]
            print(f"{nombre}: OK · última fila: {ultima}")
        except Exception as e:
            print(f"ERROR {nombre}: {e} (se conserva la copia anterior, si existe)")
    registro_path.write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
