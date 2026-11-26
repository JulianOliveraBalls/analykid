"""Informe: compila el PDF con Tectonic sobre una plantilla fija."""
import hashlib
import io
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import unicodedata
from pathlib import Path
from uuid import uuid4

import requests
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from tools.common import BASE_DIR, Context, error, respond, resultados_del_turno

OUTPUT_DIR = BASE_DIR / "output"
TIMEOUT_S = 180   # la primera compilación descarga paquetes y puede tardar
# En un servidor Linux sin Tectonic (Streamlit Community Cloud) se baja este release fijo y se
# verifica el hash antes de ejecutarlo: ni la URL ni el binario dependen de nada externo al código.
TECTONIC_LINUX_URL = ("https://github.com/tectonic-typesetting/tectonic/releases/download/"
                      "tectonic%400.17.0/tectonic-0.17.0-x86_64-unknown-linux-musl.tar.gz")
TECTONIC_LINUX_SHA256 = "8533d07f9ccbd7a65824b9e0459041bca34af1eb33daba48f59215593753a3b7"
TECTONIC_LINUX_DIR = Path.home() / ".cache" / "analykid"

# El modelo escribe solo el cuerpo; el preámbulo es fijo y sabemos que compila.
PLANTILLA = r"""\documentclass[11pt]{article}
\usepackage{fontspec}
\usepackage[spanish,es-noshorthands]{babel}
\usepackage[a4paper,margin=2.2cm,bottom=2.8cm]{geometry}
\usepackage[table]{xcolor}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{fancyhdr}
\usepackage[hidelinks]{hyperref}
\usepackage{newunicodechar}
\newunicodechar{≥}{\ensuremath{\geq}}
\newunicodechar{≤}{\ensuremath{\leq}}
\definecolor{nverde}{HTML}{2E7D32}
\definecolor{namarillo}{HTML}{F9A825}
\definecolor{nnaranja}{HTML}{EF6C00}
\definecolor{nrojo}{HTML}{C62828}
\definecolor{nsindatos}{HTML}{757575}
\newcommand{\nivelverde}{\colorbox{nverde}{\textcolor{white}{\textbf{VERDE}}}}
\newcommand{\nivelamarillo}{\colorbox{namarillo}{\textcolor{black}{\textbf{AMARILLO}}}}
\newcommand{\nivelnaranja}{\colorbox{nnaranja}{\textcolor{white}{\textbf{NARANJA}}}}
\newcommand{\nivelrojo}{\colorbox{nrojo}{\textcolor{white}{\textbf{ROJO}}}}
\newcommand{\nivelsindatos}{\colorbox{nsindatos}{\textcolor{white}{\textbf{SIN DATOS}}}}
\newcommand{\nivelnoaplica}{\colorbox{nsindatos}{\textcolor{white}{\textbf{NO APLICA}}}}
\newcommand{\nivel}[1]{\csname nivel#1\endcsname}
\newcommand{\casilla}{\framebox[0.9em]{\rule{0pt}{0.55em}}}
\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0pt}
\fancyfoot[C]{\footnotesize Este informe no reemplaza las alertas oficiales del SMN ni las indicaciones de Defensa Civil.}
\fancyfoot[R]{\footnotesize\thepage}
\title{<<TITULO>>}
\author{AnalyKid}
\date{\today}
\begin{document}
\maketitle
\thispagestyle{fancy}
<<CUERPO>>
\end{document}
"""

# Comandos que leen o escriben archivos, alteran el motor o rompen la plantilla.
# Defensa adicional a --untrusted: no es una lista exhaustiva.
PROHIBIDO = (
    r"\input", r"\include", r"\InputIfFileExists", r"\openin", r"\openout",
    r"\read", r"\write", r"\immediate", r"\special", r"\XeTeX", r"\catcode",
    r"\csname", r"\makeatletter", r"\usepackage", r"\documentclass",
    r"\verbatiminput", r"\lstinputlisting", r"\begin{document}", r"\end{document}",
    "^^",
)


# Comienzo del título de cada sección obligatoria (los títulos completos están en la skill informe_riesgo).
SECCIONES = ["Resumen", "Contexto", "Pronóstico", "Caudal", "Alertas", "Semáforo", "Medidas",
             "Escalamiento", "Checklist", "Contactos", "Fuentes", "Limitaciones"]
CITAS_POR_AMENAZA = 3
CITA = re.compile(r"\[[^\]]+ — [^\]]+\]")
# Medidas mínimas por bloque y largo mínimo de cada una (sin la cita ni comandos LaTeX):
# una línea como «revisar la malla» no dice qué mirar, cómo ni dónde.
MIN_MEDIDAS = {"Antes": 2, "Durante": 1, "Después": 2}
MIN_CARACTERES_MEDIDA = 80
ETIQUETA = re.compile(r"\\textbf\{(Antes|Durante|Después) \(")


def _plano(texto: str) -> str:
    """Minúsculas, sin tildes y sin espacios alrededor de «/», para comparar títulos y nombres."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s*/\s*", "/", sin_tildes)


def _secciones(cuerpo: str) -> dict[str, str]:
    """Título (plano) -> contenido de cada \\section."""
    partes = re.split(r"\\section\*?\{([^}]*)\}", cuerpo)
    return {_plano(partes[i]): partes[i + 1] for i in range(1, len(partes) - 1, 2)}


def _subseccion(texto: str, amenaza: str) -> str:
    """Contenido de la \\subsection cuyo título empieza con el nombre de la amenaza."""
    partes = re.split(r"\\subsection\*?\{([^}]*)\}", texto)
    buscado = _plano(amenaza.split(" /")[0])
    return next((partes[i + 1] for i in range(1, len(partes) - 1, 2)
                 if _plano(partes[i]).strip().startswith(buscado)), "")


def _bloques(apartado: str) -> dict[str, str]:
    """Texto de cada bloque \\textbf{Antes|Durante|Después (...)} del apartado de una amenaza."""
    marcas = list(ETIQUETA.finditer(apartado))
    bloques = {}
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(apartado)
        bloques.setdefault(m.group(1), apartado[m.end():fin])
    return bloques


def _medidas(bloque: str) -> list[str]:
    """Cada \\item del bloque, sin la cita ni comandos LaTeX."""
    medidas = []
    for item in re.split(r"\\item\b", bloque)[1:]:
        texto = CITA.sub("", item.split(r"\end{itemize}")[0])
        texto = re.sub(r"\\[a-zA-Z]+|[{}]", "", texto)
        medidas.append(" ".join(texto.split()))
    return medidas


def _problemas_de_medidas(nombre: str, apartado: str) -> list[str]:
    problemas = []
    for etiqueta, minimo in MIN_MEDIDAS.items():
        bloque = _bloques(apartado).get(etiqueta)
        if bloque is None:
            continue                       # ya lo informa el control de ventanas
        medidas = _medidas(bloque)
        if len(medidas) < minimo:
            problemas.append(f"Medidas de {nombre}, {etiqueta}: {len(medidas)} medida(s); se esperan al "
                             f"menos {minimo}, cada una como \\item en una lista itemize debajo de la etiqueta")
        for m in medidas:
            if len(m) < MIN_CARACTERES_MEDIDA:
                problemas.append(f"Medidas de {nombre}, {etiqueta}: «{m[:50]}» es muy corta; decí qué hacer, "
                                 f"cómo, qué mirar y dónde, con el detalle del fragmento citado")
    return problemas


def validar(cuerpo: str, riesgo: dict) -> list[str]:
    """Problemas de contenido del informe frente a la evaluación de evaluate_risk."""
    secciones = _secciones(cuerpo)
    requeridas = SECCIONES + (["Etapa"] if riesgo.get("etapa") else [])
    problemas = [f"falta la sección «{s}»" for s in requeridas
                 if not any(titulo.strip().startswith(_plano(s)) for titulo in secciones)]

    plano = _plano(cuerpo)
    for a in riesgo["amenazas"]:
        esperado = a["nivel"].replace(" ", "")
        fila = re.search(re.escape(_plano(a["amenaza"])) + r"\s*&\s*\\nivel\{(\w+)\}", plano)
        if not fila:
            problemas.append(f"el semáforo no tiene la fila «{a['amenaza']} & \\nivel{{{esperado}}}»")
        elif fila.group(1) != esperado:
            problemas.append(f"{a['amenaza']}: el semáforo dice {fila.group(1)} y evaluate_risk dio {esperado}")

    medidas = next((c for t, c in secciones.items() if t.strip().startswith("medidas")), "")
    activas = [a["amenaza"] for a in riesgo["amenazas"] if a["nivel"] in ("amarillo", "naranja", "rojo")]
    for nombre in activas:
        if _plano(nombre.split(" /")[0]) not in _plano(medidas):
            problemas.append(f"«Medidas» no tiene un apartado para {nombre}")
    for nombre, v in riesgo.get("ventanas", {}).items():
        apartado = _subseccion(medidas, nombre)
        for etiqueta, clave in (("Antes", "antes"), ("Durante", "durante"), ("Después", "despues")):
            if f"{etiqueta} ({v[clave]})" not in apartado:
                problemas.append(f"Medidas de {nombre}: falta «{etiqueta} ({v[clave]})»")
        problemas += _problemas_de_medidas(nombre, apartado)
    for nombre in activas:
        citas = len(CITA.findall(_subseccion(medidas, nombre)))
        if citas < CITAS_POR_AMENAZA:
            problemas.append(f"Medidas de {nombre}: {citas} cita(s) [Documento — Sección]; "
                             f"se esperan al menos {CITAS_POR_AMENAZA}, una por medida")
    return problemas


def _tectonic() -> str | None:
    """Ruta absoluta de Tectonic. Nada de lo que escriba el modelo decide qué se ejecuta."""
    ruta = shutil.which(os.getenv("TECTONIC_PATH", "tectonic")) or _instalar_tectonic_linux()
    return str(Path(ruta).resolve()) if ruta else None


def _instalar_tectonic_linux() -> str | None:
    """Baja Tectonic en Linux x86_64 si no está, verificando el SHA-256. None si no aplica o falla."""
    if not (sys.platform.startswith("linux") and platform.machine() == "x86_64"):
        return None
    binario = TECTONIC_LINUX_DIR / "tectonic"
    if binario.exists():
        return str(binario)
    try:
        datos = requests.get(TECTONIC_LINUX_URL, timeout=120).content
    except requests.RequestException:
        return None
    if hashlib.sha256(datos).hexdigest() != TECTONIC_LINUX_SHA256:
        return None
    TECTONIC_LINUX_DIR.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(datos)) as tar:
        binario.write_bytes(tar.extractfile("tectonic").read())
    binario.chmod(0o755)
    return str(binario)


def _escapar(texto: str) -> str:
    """Escapa los caracteres especiales de LaTeX (el título llega como texto plano)."""
    return texto.translate(str.maketrans({
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
        "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }))


# Tramos donde `&` tiene sentido y no se toca: tablas (separa columnas) y \url{} (va literal).
_CON_AMPERSAND = re.compile(r"\\url\{[^}]*\}|\\(begin|end)\{(?:tabular\*?|tabularx|longtable|array|align\*?)\}")


def escapar_ampersands(cuerpo: str) -> str:
    r"""Escapa los `&` sueltos fuera de tablas y de \url{}.

    El modelo copia nombres de las fuentes como «Texas A&M» sin escapar, aunque la skill de
    LaTeX lo pide, y la compilación fallaba siempre por eso. Se corrige acá en vez de gastar
    un reintento.
    """
    partes, abiertas, desde = [], 0, 0
    for m in _CON_AMPERSAND.finditer(cuerpo):
        tramo = cuerpo[desde:m.start()]
        partes += [tramo if abiertas else re.sub(r"(?<!\\)&", r"\\&", tramo), m.group(0)]
        if m.group(1):
            abiertas = max(0, abiertas + (1 if m.group(1) == "begin" else -1))
        desde = m.end()
    tramo = cuerpo[desde:]
    partes.append(tramo if abiertas else re.sub(r"(?<!\\)&", r"\\&", tramo))
    return "".join(partes)


def armar_tex(titulo: str, cuerpo: str) -> str:
    return PLANTILLA.replace("<<TITULO>>", _escapar(titulo)).replace("<<CUERPO>>", cuerpo)


def compilar(tectonic: str, tex: Path) -> subprocess.CompletedProcess:
    """Único punto del programa que ejecuta un proceso externo: Tectonic, con argumentos fijos."""
    return subprocess.run(
        [tectonic, "-X", "compile", "--untrusted", "--outdir", str(tex.parent), str(tex)],
        shell=False,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_S,
        cwd=tex.parent,
        env={**os.environ, "TECTONIC_UNTRUSTED_MODE": "1"},
    )


@tool
def create_pdf(titulo: str, cuerpo: str, runtime: ToolRuntime[Context]) -> Command:
    r"""Crea el PDF del plan de contingencia a partir de un título y el CUERPO LaTeX.

    `cuerpo` es solo lo que va entre \begin{document} y \end{document}: la
    herramienta agrega el preámbulo, el título y la fecha. Antes de escribirlo,
    cargá las skills «latex» e «informe_riesgo». Si la compilación falla,
    devuelve el error: corregí el cuerpo y reintentá (máximo 3 intentos).
    """
    prohibido = next((p for p in PROHIBIDO if p in cuerpo), None)
    if prohibido:
        return respond(runtime, error(
            "create_pdf", f"el cuerpo no puede contener «{prohibido}»",
            "Enviá solo contenido (secciones, listas, tablas)."))

    riesgo = resultados_del_turno(runtime.state.get("messages", [])).get("evaluate_risk")
    if riesgo is None:
        return respond(runtime, error(
            "create_pdf", "no hay evaluación de riesgo en este turno",
            "Llamá evaluate_risk antes de escribir el informe."))
    problemas = validar(cuerpo, riesgo)
    if problemas:
        return respond(runtime, error(
            "create_pdf", "el informe está incompleto",
            "Corregí y reintentá:\n- " + "\n- ".join(problemas)))

    tectonic = _tectonic()
    if tectonic is None:
        return respond(runtime, error(
            "create_pdf", "no se encontró Tectonic",
            "No reintentes: entregá el informe en markdown y avisá que falta TECTONIC_PATH."))

    cuerpo = escapar_ampersands(cuerpo)   # después de validar: el semáforo se busca con su `&`
    titulo = " ".join(titulo.split())
    ascii_titulo = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_titulo.lower()).strip("-")[:40] or "informe"
    OUTPUT_DIR.mkdir(exist_ok=True)
    tex = OUTPUT_DIR / f"{slug}-{uuid4().hex[:6]}.tex"
    tex.write_text(armar_tex(titulo, cuerpo), encoding="utf-8")

    try:
        proc = compilar(tectonic, tex)
    except subprocess.TimeoutExpired:
        return respond(runtime, error(
            "create_pdf", f"la compilación superó {TIMEOUT_S} s", "Reintentá una vez."))

    pdf = tex.with_suffix(".pdf")
    if proc.returncode != 0 or not pdf.exists():
        inicio = PLANTILLA.split("<<CUERPO>>")[0].count("\n") + 1
        salida = "\n".join((proc.stderr + proc.stdout).strip().splitlines()[-20:])[-1200:]
        return respond(runtime, error(
            "create_pdf", f"falló la compilación (el cuerpo empieza en la línea {inicio} del .tex)",
            f"Corregí el cuerpo y reintentá:\n{salida}"))
    return respond(runtime, f"PDF creado: {pdf.name}", artifact={"pdf": str(pdf), "latex": cuerpo})
