"""Informe: compila el PDF con Tectonic sobre una plantilla fija."""
import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from uuid import uuid4

from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from tools.common import BASE_DIR, Context, error, respond, resultados_del_turno

OUTPUT_DIR = BASE_DIR / "output"
TIMEOUT_S = 180   # la primera compilación descarga paquetes y puede tardar

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
CITA = re.compile(r"\[[^\]]+ — [^\]]+\]")


def _plano(texto: str) -> str:
    """Minúsculas, sin tildes y sin espacios alrededor de «/», para comparar títulos y nombres."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s*/\s*", "/", sin_tildes)


def _secciones(cuerpo: str) -> dict[str, str]:
    """Título (plano) -> contenido de cada \\section."""
    partes = re.split(r"\\section\*?\{([^}]*)\}", cuerpo)
    return {_plano(partes[i]): partes[i + 1] for i in range(1, len(partes) - 1, 2)}


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
    if activas and len(CITA.findall(medidas)) < 2 * len(activas):
        problemas.append(f"«Medidas» tiene {len(CITA.findall(medidas))} citas [Documento — Sección]; "
                         f"se esperan al menos {2 * len(activas)} (2 por amenaza activa)")
    return problemas


def _tectonic() -> str | None:
    """Ruta absoluta de Tectonic. Nada de lo que escriba el modelo decide qué se ejecuta."""
    ruta = shutil.which(os.getenv("TECTONIC_PATH", "tectonic"))
    return str(Path(ruta).resolve()) if ruta else None


def _escapar(texto: str) -> str:
    """Escapa los caracteres especiales de LaTeX (el título llega como texto plano)."""
    return texto.translate(str.maketrans({
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
        "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }))


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
