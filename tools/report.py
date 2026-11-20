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

from tools.common import BASE_DIR, Context, error, respond

OUTPUT_DIR = BASE_DIR / "output"
TIMEOUT_S = 180   # la primera compilación descarga paquetes y puede tardar

# El modelo escribe solo el cuerpo; el preámbulo es fijo y sabemos que compila.
PLANTILLA = r"""\documentclass[11pt]{article}
\usepackage{fontspec}
\usepackage[spanish]{babel}
\usepackage[a4paper,margin=2.5cm]{geometry}
\usepackage{booktabs}
\usepackage[hidelinks]{hyperref}
\title{<<TITULO>>}
\author{}
\date{\today}
\begin{document}
\maketitle
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
