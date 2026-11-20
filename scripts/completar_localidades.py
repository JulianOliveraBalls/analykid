"""Agrega a datos/localidades.json los campos rio, piedemonte y emergencias.

No toca ningún otro campo. Si un campo ya existe, lo conserva (usar --forzar para pisarlo).
Funciona con el archivo como objeto {clave: {...}} o como lista de objetos con "nombre".

Uso:
    python scripts/completar_localidades.py            # muestra los cambios sin escribir
    python scripts/completar_localidades.py --escribir
"""
import json
import sys
import unicodedata
from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "datos" / "localidades.json"

# Río asignado (spec, sección 7 de la v2). San Rafael usa el Diamante en la demo.
RIO = {
    "mendoza": "mendoza", "godoy_cruz": "mendoza", "guaymallen": "mendoza", "las_heras": "mendoza",
    "lujan_de_cuyo": "mendoza", "maipu": "mendoza", "lavalle": "mendoza", "uspallata": "mendoza",
    "potrerillos": "mendoza",
    "tupungato": "tunuyan", "tunuyan": "tunuyan", "san_carlos": "tunuyan", "san_martin": "tunuyan",
    "junin": "tunuyan", "rivadavia": "tunuyan", "santa_rosa": "tunuyan", "la_paz": "tunuyan",
    "san_rafael": "diamante",
    "general_alvear": "atuel", "malargue": "atuel",
}

# PROPUESTA A VALIDAR: localidades en piedemonte o zona de montaña con riesgo aluvional.
PIEDEMONTE = {"mendoza", "godoy_cruz", "las_heras", "lujan_de_cuyo", "uspallata", "potrerillos",
              "tupungato", "tunuyan", "san_carlos", "malargue"}

# Contactos encontrados en prensa: confirmar en el sitio del municipio y completar "verificado".
EMERGENCIAS = {
    "tupungato": {
        "defensa_civil_municipal": "2622 574912",
        "fuente": "https://elcucodigital.com/innovacion-en-seguridad-tupungato-implementa-codigos-qr-para-prevenir-emergencias/",
    },
    "san_rafael": {
        "defensa_civil_municipal": "2604-325012 (fijo) · WhatsApp 2604-807949",
        "fuente": "https://www.sitioandino.com.ar/departamentales/alerta-pasos-badenes-san-rafael-erogaciones-el-rio-diamante-n5724975",
    },
}


def clave_de(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "_".join(sin_tildes.lower().replace("-", " ").split())


def completar(clave: str, loc: dict, forzar: bool) -> list[str]:
    cambios = []
    nuevos = {
        "rio": RIO.get(clave),
        "piedemonte": clave in PIEDEMONTE,
        "emergencias": {"general": "911", "defensa_civil_municipal": None, "fuente": None,
                        "verificado": None, **EMERGENCIAS.get(clave, {})},
    }
    for campo, valor in nuevos.items():
        if campo in loc and not forzar:
            continue
        if campo == "rio" and valor is None:
            cambios.append(f"  ! {clave}: sin río asignado, revisar a mano")
            continue
        loc[campo] = valor
        cambios.append(f"  + {clave}.{campo} = {json.dumps(valor, ensure_ascii=False)}")
    return cambios


def main() -> None:
    escribir, forzar = "--escribir" in sys.argv, "--forzar" in sys.argv
    datos = json.loads(RUTA.read_text(encoding="utf-8"))
    if isinstance(datos, dict) and isinstance(datos.get("localidades"), (dict, list)):
        contenedor = datos["localidades"]
    else:
        contenedor = datos
    items = (contenedor.items() if isinstance(contenedor, dict)
             else ((clave_de(l.get("clave") or l.get("nombre", "")), l) for l in contenedor))
    vistos = set()
    for clave, loc in items:
        clave = clave_de(clave)
        vistos.add(clave)
        for linea in completar(clave, loc, forzar):
            print(linea)
    for faltante in sorted(set(RIO) - vistos):
        print(f"  ? {faltante} está en el mapeo pero no en localidades.json (revisar el nombre)")
    if escribir:
        RUTA.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Escrito: {RUTA}")
    else:
        print("Vista previa. Repetí con --escribir para guardar.")


if __name__ == "__main__":
    main()
