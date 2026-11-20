"""Agrega a datos/localidades.json los campos rio, piedemonte y emergencias.

No toca ningún otro campo. Si un campo ya existe, lo conserva; --campo emergencias pisa solo ese
(--forzar pisa todos).
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

# Defensa Civil municipal: solo números publicados en el sitio oficial del municipio.
# "verificado" es la fecha en que se leyó esa página (no se llamó al número).
VERIFICADO = "2026-11-20"
EMERGENCIAS = {
    "mendoza": ("0261 444-1010 / 444-3664 / 444-3638",
                "https://prensa.ciudaddemendoza.gob.ar/2023/11/17/la-ciudad-en-alerta-ante-la-presencia-del-zonda/"),
    "godoy_cruz": ("261 596-1532 (guardia de Protección Civil)",
                   "https://www.godoycruz.gob.ar/servicios-al-vecino/telefonos-utiles/"),
    "guaymallen": ("0261 421-6147", "https://www.guaymallen.gob.ar/importante/"),
    "lujan_de_cuyo": ("0261 212-4022", "https://lujandecuyo.gob.ar/defensa-civil/"),
    "potrerillos": ("0261 212-4022 (Defensa Civil de Luján de Cuyo)",
                    "https://lujandecuyo.gob.ar/distrito-potrerillos/"),
    "tupungato": ("2622 574912 (guardia 24 h)", "https://tupungato.gov.ar/?page_id=2276"),
    "san_rafael": ("2604 325012 / 2604 807949", "https://www.sanrafael.gov.ar/telefonos-utiles/"),
    "general_alvear": ("2625 668303",
                       "https://alvearmendoza.gob.ar/defensa-civil-informo-sobre-los-focos-de-incendio-registrados-en-general-alvear/"),
    "malargue": ("2604 030972",
                 "https://www.malargue.gov.ar/conoce-los-telefonos-utiles-para-comunicarte-con-las-distintas-areas-municipales/"),
}

# Dirección de Contingencias Climáticas: recibe las denuncias de daño agrícola (granizo, helada).
# Una delegación por oasis, según la página oficial de denuncias.
FUENTE_CONTINGENCIAS = "https://www.mendoza.gov.ar/contingencias/riesgo-agricola"
CONTINGENCIAS = {
    "norte": ("sede central (Ciudad de Mendoza)", "0261 385-4270"),
    "alta_montana": ("sede central (Ciudad de Mendoza)", "0261 385-4270"),
    "valle_de_uco": ("delegación Valle de Uco (Tunuyán)", "02622 423036"),
    "este": ("delegación Este (San Martín)", "0263 442-0365"),
    "sur": ("delegación Sur (San Rafael)", "0260 443-8052"),
}


def emergencias(clave: str, oasis: str) -> dict:
    municipal, fuente = EMERGENCIAS.get(clave, (None, None))
    delegacion, telefono = CONTINGENCIAS[oasis]
    return {
        "general": "911",
        "defensa_civil_municipal": municipal,
        "fuente": fuente,
        "verificado": VERIFICADO if municipal else None,
        "contingencias_climaticas": {"delegacion": delegacion, "telefono": telefono,
                                     "fuente": FUENTE_CONTINGENCIAS, "verificado": VERIFICADO},
    }


def clave_de(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "_".join(sin_tildes.lower().replace("-", " ").split())


def completar(clave: str, loc: dict, forzar: bool, pisar: set[str]) -> list[str]:
    cambios = []
    nuevos = {
        "rio": RIO.get(clave),
        "piedemonte": clave in PIEDEMONTE,
        "emergencias": emergencias(clave, loc["oasis"]),
    }
    for campo, valor in nuevos.items():
        if campo in loc and not (forzar or campo in pisar):
            continue
        if campo == "rio" and valor is None:
            cambios.append(f"  ! {clave}: sin río asignado, revisar a mano")
            continue
        loc[campo] = valor
        cambios.append(f"  + {clave}.{campo} = {json.dumps(valor, ensure_ascii=False)}")
    return cambios


def formatear(datos) -> str:
    """Una localidad por línea, como el archivo original, para que los diffs sean legibles."""
    if not (isinstance(datos, dict) and isinstance(datos.get("localidades"), dict)):
        return json.dumps(datos, ensure_ascii=False, indent=2) + "\n"
    cabecera = [f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}"
                for k, v in datos.items() if k != "localidades"]
    filas = [f"    {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}"
             for k, v in datos["localidades"].items()]
    return "{\n" + ",\n".join(cabecera + ['  "localidades": {\n' + ",\n".join(filas) + "\n  }"]) + "\n}\n"


def main() -> None:
    escribir, forzar = "--escribir" in sys.argv, "--forzar" in sys.argv
    pisar = {sys.argv[i + 1] for i, a in enumerate(sys.argv[:-1]) if a == "--campo"}
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
        for linea in completar(clave, loc, forzar, pisar):
            print(linea)
    for faltante in sorted(set(RIO) - vistos):
        print(f"  ? {faltante} está en el mapeo pero no en localidades.json (revisar el nombre)")
    if escribir:
        RUTA.write_text(formatear(datos), encoding="utf-8")
        print(f"Escrito: {RUTA}")
    else:
        print("Vista previa. Repetí con --escribir para guardar.")


if __name__ == "__main__":
    main()
