"""UI de Streamlit para AnalyKid.

Cada respuesta tiene dos partes: el recorrido del agente, paso a paso (en cada
paso, la cadena de pensamiento del modelo y, por cada tool, la invocación, los
parámetros que le pasó y el resultado que recibió), y debajo la respuesta final
con el botón del PDF. Los datos de las tools (semáforo, pronóstico, caudal,
contactos) van en la primera página del PDF. La lógica vive en agente.py; acá
solo se dibujan los eventos que emite.

Ejecutar con:  streamlit run app.py
"""
import base64
import html
import json
import os
import re
from pathlib import Path

import streamlit as st

DIR = Path(__file__).parent
LOGO = DIR / "assets" / "analykid-logo.svg"
ICONO = str(DIR / "assets" / "analykid-logo.png")   # pestaña del navegador

st.set_page_config(page_title="AnalyKid", page_icon=ICONO, layout="wide")

# En Streamlit Community Cloud las keys llegan como Secrets, que Streamlit pasa al entorno recién
# cuando alguien lee st.secrets; model.py las busca al importarse, así que se copian antes.
# También se aceptan dentro de una sección ([general], [secrets]…), un error común al pegarlas.
_SECRETS: list[str] = []   # solo los nombres, para el mensaje de error
try:
    if st.secrets.load_if_toml_exists():
        for _clave, _valor in st.secrets.items():
            for _k, _v in (_valor.items() if hasattr(_valor, "items") else [(_clave, _valor)]):
                _SECRETS.append(_k)
                os.environ.setdefault(_k, str(_v))
except Exception as e:   # TOML inválido, por ejemplo pegado con formato .env (KEY=valor sin comillas)
    st.error(f"No se pudieron leer los Secrets: {type(e).__name__}. Revisá que cada línea sea "
             'CLAVE = "valor", con comillas.')
    st.stop()

try:
    from agente import (
        MODELO, list_threads, new_thread, resume_thread, saved_turns, select_thread, stream_turn,
    )
except RuntimeError as e:  # por ejemplo, faltan API keys en el .env
    st.error(f"{e} En Streamlit Community Cloud se cargan en Settings → Secrets. "
             f"Secrets que ve la app: {', '.join(_SECRETS) or 'ninguno'}.")
    st.stop()


@st.cache_resource(show_spinner="Preparando la base de conocimiento (solo la primera vez)…")
def _preparar_rag() -> None:
    """Arma la base vectorial si no existe: en la nube no se versiona y hay que ingestar al arrancar."""
    from rag.store import DB_DIR
    if not DB_DIR.exists():
        from rag import ingest
        ingest.main()


_preparar_rag()

LOCALIDADES = json.loads((DIR / "datos" / "localidades.json").read_text(encoding="utf-8"))["localidades"]
PERFILES = {"vid": "Vid", "frutal": "Frutal", "hortaliza": "Hortaliza", "urbano": "Urbano"}
EJEMPLOS = [
    ("Vid en Tupungato", "Armame el plan de contingencia para una finca de vid de 10 hectáreas "
                         "en Tupungato para los próximos 7 días"),
    ("Frutal en San Rafael", "Armame el plan de contingencia para una finca de frutales de 25 "
                             "hectáreas en San Rafael para los próximos 5 días"),
    ("Zona urbana en Luján de Cuyo", "Armame el plan de contingencia para la zona urbana de "
                                     "Luján de Cuyo, perfil urbano, para los próximos 7 días"),
]
# Qué es cada tool y de dónde saca el dato, para el recorrido del agente.
TITULOS = {
    "get_enso_status": ("Estado de El Niño", "NOAA, índice RONI"),
    "get_weather_forecast": ("Pronóstico", "Open-Meteo"),
    "get_river_discharge": ("Caudal del río", "Flood API, GloFAS"),
    "web_search": ("Alertas oficiales", "Tavily sobre dominios oficiales"),
    "evaluate_risk": ("Evaluación de riesgo", "umbrales en código, lee el estado"),
    "search_knowledge_base": ("Base de conocimiento", "RAG propio"),
    "load_skill": ("Skill", "instrucciones en skills/"),
    "create_pdf": ("Informe PDF", "control de contenido y Tectonic"),
}
ALTO_BLOQUE = 240      # px: los resultados largos (skills, RAG, LaTeX) se recorren con scroll
LINEAS_SIN_SCROLL = 9


st.markdown("""
<style>
:root {--ak-navy: #0B1F5C; --ak-azul: #1226B4; --ak-tinta: #1A1D26; --ak-gris: #6B7280;
  --ak-hilo: #D9DEEA; --ak-fondo: #F3F5FB;
  --ak-verde: #1F8A4C; --ak-amarillo: #D9A400; --ak-naranja: #E36A00; --ak-rojo: #C1272D;}
/* Sin ancho máximo: con uno, el bloque se centra y el encabezado queda en el medio. */
[data-testid="stMainBlockContainer"].block-container {padding-top: 1rem !important;
  max-width: none !important; margin-left: 0 !important;}
.ak-hero {justify-content: flex-start; text-align: left;}
.ak-hero p {font-size: 1.05rem;}
/* La franja superior de Streamlit se pinta de blanco al plegar la barra y tapa el encabezado:
   transparente y sin capturar clics, salvo sus botones (desplegar la barra, menú). */
[data-testid="stHeader"] {background: transparent !important; pointer-events: none;}
[data-testid="stHeader"] button, [data-testid="stHeader"] a {pointer-events: auto;}
/* Nombre de la app arriba a la izquierda de la barra lateral. */
[data-testid="stSidebarUserContent"] {padding-top: 0 !important;}
.ak-marca {color: var(--ak-navy); font-size: 1.6rem; font-weight: 600; letter-spacing: -.01em;
  margin: -2.6rem 0 .6rem; line-height: 1.2;}
/* Inicio sin conversación: bienvenida y caja de texto al centro de la pantalla, como un chat. */
.st-key-ak-inicio {min-height: 62vh; justify-content: center; max-width: 780px; margin: 0 auto;}
.st-key-ak-inicio h4 {text-align: center; color: var(--ak-navy);}
/* Mensaje de la persona: burbuja a la derecha con el azul marino de la marca, como en un chat. */
.ak-burbuja {background: var(--ak-navy); color: #fff; border-radius: 16px 16px 4px 16px;
  padding: 10px 16px; max-width: min(60%, 560px); width: fit-content; margin: 14px 0 10px auto;
  line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere;}
.ak-hero {display: flex; align-items: center; gap: 16px; padding: 2px 0 14px;
  border-bottom: 1.5px solid var(--ak-navy); margin-bottom: 18px;}
.ak-hero img {height: 52px;}
.ak-hero h1 {color: var(--ak-navy); font-size: 1.9rem; font-weight: 600; margin: 0; padding: 0;
  letter-spacing: -.01em;}
.ak-hero p {margin: 2px 0 0; color: var(--ak-gris); font-size: .95rem;}
.ak-seccion {font-size: .78rem; text-transform: uppercase; letter-spacing: .09em; font-weight: 600;
  color: var(--ak-azul); display: flex; align-items: center; gap: 10px; margin: 18px 0 8px;}
.ak-seccion::after {content: ""; flex: 1; border-top: 1px solid var(--ak-hilo);}
.ak-card {border: 1px solid var(--ak-hilo); border-top: 4px solid var(--ak-gris); border-radius: 8px;
  padding: 10px 12px; min-height: 124px; background: #fff;}
.ak-card .ak-amenaza {font-size: .74rem; text-transform: uppercase; letter-spacing: .07em;
  color: var(--ak-gris); font-weight: 600;}
.ak-card .ak-nivel {font-size: 1.2rem; font-weight: 600; color: var(--ak-tinta); margin: 4px 0;
  display: flex; align-items: center; gap: 8px;}
.ak-card .ak-motivo {font-size: .8rem; line-height: 1.3; color: var(--ak-tinta);}
.ak-punto {display: inline-block; width: .7em; height: .7em; border-radius: 50%;
  background: var(--ak-gris); flex: none;}
.ak-verde {border-top-color: var(--ak-verde);}
.ak-amarillo {border-top-color: var(--ak-amarillo);}
.ak-naranja {border-top-color: var(--ak-naranja);}
.ak-rojo {border-top-color: var(--ak-rojo);}
.ak-verde .ak-punto, .ak-punto.ak-verde {background: var(--ak-verde);}
.ak-amarillo .ak-punto, .ak-punto.ak-amarillo {background: var(--ak-amarillo);}
.ak-naranja .ak-punto, .ak-punto.ak-naranja {background: var(--ak-naranja);}
.ak-rojo .ak-punto, .ak-punto.ak-rojo {background: var(--ak-rojo);}
.ak-titulo {display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; margin: 4px 0 10px;}
.ak-titulo h3 {margin: 0; padding: 0; color: var(--ak-navy); font-weight: 600;}
.ak-chip {display: inline-flex; align-items: center; gap: 6px; border-radius: 999px;
  padding: 2px 10px; font-size: .8rem; background: var(--ak-fondo); color: var(--ak-navy);}
.ak-etiqueta {font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; font-weight: 600;
  color: var(--ak-gris); margin: 10px 0 4px;}
.ak-razonamiento {border-left: 2px solid var(--ak-azul); background: var(--ak-fondo);
  padding: 8px 12px; color: var(--ak-tinta); margin: 0 0 8px; font-size: .9rem; line-height: 1.45;}
.ak-invocacion {display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
  border-top: 1px solid var(--ak-hilo); padding-top: 10px; margin-top: 12px;}
.ak-invocacion .ak-n {font-size: .78rem; font-weight: 600; color: var(--ak-azul);}
.ak-invocacion code {font-size: .95rem; font-weight: 600; color: var(--ak-navy);
  background: var(--ak-fondo); padding: 1px 8px; border-radius: 4px;}
.ak-invocacion .ak-que {font-size: .85rem; color: var(--ak-gris);}
.ak-estado {font-size: .7rem; text-transform: uppercase; letter-spacing: .08em; font-weight: 600;
  border-radius: 4px; padding: 1px 7px; margin-left: 6px;}
.ak-estado.ak-ok {color: var(--ak-verde); border: 1px solid var(--ak-verde);}
.ak-estado.ak-error {color: var(--ak-rojo); border: 1px solid var(--ak-rojo);}
.ak-estado.ak-espera {color: var(--ak-gris); border: 1px solid var(--ak-hilo);}
/* Mientras un paso del recorrido corre, su título brilla de izquierda a derecha. */
@keyframes ak-brillo {from {background-position: 200% 0;} to {background-position: -200% 0;}}
[class*="st-key-ak-recorrido"] summary:has([data-testid="stExpanderIconSpinner"]) p {
  background: linear-gradient(90deg, var(--ak-gris) 30%, var(--ak-azul) 50%, var(--ak-gris) 70%);
  background-size: 200% 100%; -webkit-background-clip: text; background-clip: text;
  color: transparent; animation: ak-brillo 2.2s linear infinite;}
/* El mapa capturaba la rueda del mouse (zoom) y la página dejaba de scrollear al pasar por
   encima: queda fijo, con los botones + / − para el zoom. */
[data-testid="stDeckGlJsonChart"] {pointer-events: none;}
[data-testid="stDeckGlJsonChartZoomButton"], [data-testid="stDeckGlJsonChartZoomButton"] * {
  pointer-events: auto;}
/* Barra lateral: conversaciones como lista de texto, sin caja; la actual, resaltada. */
[class*="st-key-ak-lista"] button {justify-content: flex-start; padding: 6px 10px;
  border-radius: 8px; color: var(--ak-tinta); min-height: 0;}
[class*="st-key-ak-lista"] button > div {justify-content: flex-start; min-width: 0;}
[class*="st-key-ak-lista"] button p {white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  text-align: left; font-size: .9rem;}
[class*="st-key-ak-lista"] button:hover {background: rgba(11, 31, 92, .07); color: var(--ak-navy);}
.st-key-ak-lista-conversaciones button:disabled {background: rgba(11, 31, 92, .10);
  color: var(--ak-navy); opacity: 1; cursor: default;}
.st-key-ak-lista-conversaciones button:disabled p {font-weight: 600;}
.st-key-ak-lista-nueva button p {font-weight: 600;}
/* La lista se redibuja al final de la página: mientras el agente trabaja, Streamlit la marca
   como vieja y la atenúa. Se ve igual que siempre. */
[class*="st-key-ak-lista"] [data-stale="true"] {opacity: 1 !important;}
</style>
""", unsafe_allow_html=True)


def _seccion(titulo: str) -> None:
    st.markdown(f'<div class="ak-seccion">{titulo}</div>', unsafe_allow_html=True)


def _etiqueta(texto: str, estado: str = "") -> None:
    marca = {"ok": '<span class="ak-estado ak-ok">ok</span>',
             "error": '<span class="ak-estado ak-error">error</span>',
             "espera": '<span class="ak-estado ak-espera">en curso</span>'}.get(estado, "")
    st.markdown(f'<div class="ak-etiqueta">{texto}{marca}</div>', unsafe_allow_html=True)


def _bloque(texto: str, lenguaje: str | None = None) -> None:
    """Texto exacto en un bloque de código; los largos quedan con altura fija y scroll."""
    largo = texto.count("\n") >= LINEAS_SIN_SCROLL or len(texto) > 900
    st.code(texto, language=lenguaje, wrap_lines=True, **({"height": ALTO_BLOQUE} if largo else {}))



def init_session(config) -> None:
    """Carga en session_state la conversación indicada (vacía si es nueva)."""
    st.session_state.config = config
    st.session_state.historial = saved_turns(config)   # lista de (pregunta, eventos)


# --- Recorrido del agente: un paso por cada respuesta del modelo -----------------

class Turno:
    """Acumula lo que devolvieron las tools en un turno, para el panel de resultado."""

    def __init__(self):
        self.datos: dict[str, object] = {}       # nombre de la tool -> último artifact válido
        self.llamadas: set[str] = set()          # tools llamadas (aunque hayan fallado)
        self.fuentes: list[dict] = []
        self.textos: list[tuple[int, str]] = []  # (posición del evento, texto)
        self.ultima_llamada = -1
        self.errores = 0
        self.pasos = 0


def _rotulo_paso(n: int, nombres: list[str], errores: int) -> tuple[str, str]:
    """Rótulo y estado de un paso terminado."""
    if nombres:
        detalle = ", ".join(dict.fromkeys(nombres))
        if len(nombres) > 1:
            detalle += f" ({len(nombres)} llamadas en paralelo)"
    else:
        detalle = "respuesta del modelo, sin tools"
    if errores:
        detalle += f" · {errores} con error"
    return f"Paso {n} · {detalle}", "error" if errores else "complete"


def _rotulo_recorrido(pasos: int, llamadas: int, errores: int) -> str:
    return (f"Recorrido del agente · {pasos} paso(s) · {llamadas} llamada(s) a tools"
            + (f" · {errores} con error" if errores else ""))


def _rotulos(eventos: list[dict]) -> tuple[list[tuple[str, str]], str]:
    """Rótulos finales de cada paso y del recorrido de un turno ya guardado.

    En el historial cada caja se crea con su rótulo final. Si se creara con uno provisional y se
    actualizara al final, como en vivo, cada re-ejecución de la página la haría parpadear.
    """
    pasos: list[dict] = []
    de_llamada: dict[str, dict] = {}   # id de la llamada -> paso que la pidió
    anterior = "resultado"
    for e in eventos:
        if e["tipo"] == "fuentes":
            continue
        if e["tipo"] != "resultado" and anterior == "resultado":   # mismo corte que el recorrido
            pasos.append({"nombres": [], "errores": 0})
        anterior = e["tipo"]
        if e["tipo"] == "llamada":
            pasos[-1]["nombres"].append(e["nombre"])
            de_llamada[e["id"]] = pasos[-1]
        elif e["tipo"] == "resultado" and e["texto"].startswith("ERROR"):
            de_llamada[e["id"]]["errores"] += 1
    rotulos = [_rotulo_paso(n, p["nombres"], p["errores"]) for n, p in enumerate(pasos, 1)]
    llamadas = sum(len(p["nombres"]) for p in pasos)
    return rotulos, _rotulo_recorrido(len(pasos), llamadas, sum(p["errores"] for p in pasos))


class Paso:
    """Un paso del ciclo del agente: lo que el modelo pensó y las tools que pidió en esa respuesta.

    Las tools de un mismo paso se piden juntas (en paralelo); el paso se cierra cuando el
    modelo vuelve a responder. Sin `rotulo` es un paso en vivo; con él, uno del historial.
    """

    def __init__(self, n: int, rotulo: tuple[str, str] | None = None):
        self.n = n
        self.vivo = rotulo is None
        self.nombres: list[str] = []
        self.errores = 0
        self.con_pensamiento = False
        # Abierto mientras el agente trabaja (la consigna pide ver cada tool en vivo); en el
        # historial queda plegado y se abre a demanda, como el razonamiento de un chat.
        etiqueta, estado = rotulo or (f"Paso {n}", "running")
        self.caja = st.status(etiqueta, expanded=self.vivo, state=estado)

    def pensamiento(self) -> None:
        """Encabezado de la cadena de pensamiento, una sola vez por paso."""
        if not self.con_pensamiento:
            _etiqueta("Cadena de pensamiento")
            self.con_pensamiento = True

    def cerrar(self) -> None:
        # Se pliega al terminar: queda a la vista el paso que corre y los anteriores se abren
        # a demanda. Un paso que la persona abre después ya no recibe cambios y queda abierto.
        if self.vivo:
            etiqueta, estado = _rotulo_paso(self.n, self.nombres, self.errores)
            self.caja.update(label=etiqueta, state=estado, expanded=False)


def _invocacion(paso: Paso, e: dict) -> dict:
    """Dibuja la invocación y los parámetros; devuelve los huecos donde irá el resultado."""
    que, fuente = TITULOS.get(e["nombre"], (e["nombre"], ""))
    st.markdown(
        f'<div class="ak-invocacion"><span class="ak-n">{paso.n}.{len(paso.nombres)}</span>'
        f'<span>Invocación</span><code>{html.escape(e["nombre"])}</code>'
        f'<span class="ak-que">{que}{" · " + fuente if fuente else ""}</span></div>',
        unsafe_allow_html=True)
    izq, der = st.columns([2, 3])
    with izq:
        _etiqueta("Parámetros que pasa el modelo")
        if e["args"]:
            _bloque(json.dumps(e["args"], ensure_ascii=False, indent=2), "json")
        else:
            st.caption("Sin parámetros: la tool usa sus valores por defecto.")
    with der:
        titulo, cuerpo = st.empty(), st.empty()
        with titulo:
            _etiqueta("Resultado que recibe el modelo", "espera")
        cuerpo.caption("Esperando la respuesta de la tool…")
    return {"llamada": e, "paso": paso, "titulo": titulo, "cuerpo": cuerpo}


def render_recorrido(eventos, turno: Turno, rotulos: list[tuple[str, str]] | None) -> list[dict]:
    """Dibuja el recorrido a medida que llegan los eventos. Devuelve los eventos dibujados.

    Cada respuesta del modelo abre un paso: primero su cadena de pensamiento (el
    razonamiento que expone el modelo y lo que anuncia) y después, por cada tool que
    pidió, la invocación, los parámetros y el resultado.
    """
    emitidos, pendientes, finales = [], {}, {}
    paso, anterior = None, "resultado"
    for pos, e in enumerate(eventos):
        emitidos.append(e)
        tipo = e["tipo"]
        if tipo == "fuentes":
            turno.fuentes = e["fuentes"]
            continue
        if tipo != "resultado" and anterior == "resultado":   # el modelo volvió a responder
            if paso:
                paso.cerrar()
            turno.pasos += 1
            paso = Paso(turno.pasos, rotulos[turno.pasos - 1] if rotulos else None)
        anterior = tipo
        if tipo == "resultado":
            hueco = pendientes.pop(e["id"])
            llamada = hueco["llamada"]
            error = e["texto"].startswith("ERROR")
            turno.errores += error
            hueco["paso"].errores += error
            if not error and e["datos"]:
                turno.datos[llamada["nombre"]] = e["datos"]
            with hueco["titulo"]:
                _etiqueta("Resultado que recibe el modelo", "error" if error else "ok")
            with hueco["cuerpo"].container():
                _bloque(e["texto"] or "(sin texto)")
            continue
        with paso.caja:
            if tipo == "razonamiento":
                paso.pensamiento()
                # Gemini titula sus resúmenes con **negrita**: es el único markdown que se respeta.
                texto = "<br>".join(html.escape(l.strip()) for l in e["texto"].splitlines() if l.strip())
                texto = re.sub(r"\*\*(.+?)\*\*", r"<b>\g<1></b>", texto)
                st.markdown(f'<div class="ak-razonamiento">{texto}</div>', unsafe_allow_html=True)
            elif tipo == "texto":
                paso.pensamiento()
                finales[pos] = st.empty()
                finales[pos].markdown(e["texto"])
                turno.textos.append((pos, e["texto"]))
            elif tipo == "llamada":
                if not paso.con_pensamiento:
                    paso.pensamiento()
                    st.caption("El modelo no devolvió razonamiento ni texto en este paso: "
                               "pidió las tools directamente.")
                turno.ultima_llamada = pos
                turno.llamadas.add(e["nombre"])
                paso.nombres.append(e["nombre"])
                pendientes[e["id"]] = _invocacion(paso, e)
    if paso:
        paso.cerrar()
    # La respuesta final (texto posterior a la última tool) se muestra fuera del recorrido.
    for pos, _ in turno.textos:
        if pos > turno.ultima_llamada:
            finales[pos].caption("Es la respuesta final: se muestra abajo, fuera del recorrido.")
    return emitidos


# --- Un turno completo ---------------------------------------------------------------

EMOJI_NIVEL = {"verde": "🟢", "amarillo": "🟡", "naranja": "🟠", "rojo": "🔴"}
EMOJI_AMENAZA = [("Sanitari", "🍇"), ("Pluvial", "🌧️"), ("Granizo", "⛈️"), ("Tormenta", "⛈️"),
                 ("Aluvional", "⛰️"), ("Crecida", "🌊")]
_NIVEL = re.compile(r"(?<![🟢🟡🟠🔴] )(?<!\w)(verde|amarillo|naranja|rojo)\b", re.IGNORECASE)
# Amenaza al empezar un renglón o una viñeta, seguida de «:» o «(» («Sanitaria: …», «**Pluvial** (…)»).
_AMENAZA = re.compile(r"^(\s*(?:[-*]|\d+\.)?\s*(?:\*\*)?)((?:Sanitari|Pluvial|Granizo|Tormenta|Aluvional|Crecida)[^:(\n]{0,40}?"
                      r"(?:\*\*)?\s*[:(])", re.IGNORECASE | re.MULTILINE)


def _con_emojis(texto: str) -> str:
    """Respuesta final con un emoji por nivel y por amenaza, y las citas en azul y en cursiva.

    Las citas `[Documento — Sección]` se muestran distintas para que se lean como fuente y no como
    parte de la respuesta; su texto no se toca.
    """
    def amenaza(m: re.Match) -> str:
        emoji = next(e for clave, e in EMOJI_AMENAZA if m.group(2).lower().startswith(clave.lower()))
        return f"{m.group(1)}{emoji} {m.group(2)}"

    partes = re.split(r"(\[[^\]]*\])", texto)   # las posiciones impares son lo que va entre corchetes
    for i, parte in enumerate(partes):
        if i % 2:
            if " — " in parte:   # cita del RAG: en azul y en cursiva, con sus corchetes
                partes[i] = f":blue[*{parte.replace('*', '')}*]"
            continue
        parte = _NIVEL.sub(lambda m: f"{EMOJI_NIVEL[m.group(1).lower()]} {m.group(1)}", parte)
        partes[i] = _AMENAZA.sub(amenaza, parte)
    return "".join(partes)


def render_turno(eventos, clave: str, vivo: bool) -> list[dict]:
    """Recorrido arriba y, debajo, la respuesta final con el PDF. Sirve en vivo y para el historial.

    Mientras el agente trabaja, «Armando plan de contingencia…» queda abierto y cada paso se ve
    en vivo con sus tools, parámetros y resultados. Al terminar, el recorrido se pliega con su
    resumen y debajo quedan la respuesta y el botón del PDF: exactamente lo mismo que dibuja el
    historial, para que la próxima re-ejecución no cambie nada en pantalla. Los datos (semáforo,
    pronóstico, caudal, contactos) van en el propio PDF.
    """
    turno = Turno()
    rotulos, resumen = (None, "Armando plan de contingencia…") if vivo else _rotulos(eventos)
    with st.container(key=f"ak-recorrido-{clave}"):
        caja = st.status(resumen, expanded=vivo, state="running" if vivo else "complete")
        with caja:
            st.caption("Cada paso es una respuesta del modelo: su cadena de pensamiento y, por cada "
                       "tool, la invocación, los parámetros y el resultado.")
            emitidos = render_recorrido(eventos, turno, rotulos)
        if vivo:
            n = sum(e["tipo"] == "llamada" for e in emitidos)
            caja.update(label=_rotulo_recorrido(turno.pasos, n, turno.errores), state="complete",
                        expanded=False)
    if finales := [texto for pos, texto in turno.textos if pos > turno.ultima_llamada]:
        _seccion("Respuesta final")
        for texto in finales:
            st.markdown(_con_emojis(texto))
    pdf = turno.datos.get("create_pdf")
    if pdf and Path(pdf["pdf"]).exists():
        st.download_button("Descargar plan (PDF)", Path(pdf["pdf"]).read_bytes(), file_name=Path(pdf["pdf"]).name,
                           mime="application/pdf", key=f"{clave}-pdf", type="primary", icon=":material/download:")
    elif pdf:
        st.caption("El PDF de esta conversación ya no está en el servidor: pedí el plan de nuevo para generarlo.")
    return emitidos


# --- Barra lateral --------------------------------------------------------------------

def render_sidebar() -> tuple:
    """Barra lateral. Devuelve los contenedores de la lista de conversaciones, vacíos.

    La lista se llena al final de la página (`render_conversaciones`), así refleja el turno que
    acaba de terminar sin volver a ejecutar la página entera.
    """
    with st.sidebar:
        st.markdown('<div class="ak-marca">AnalyKid</div>', unsafe_allow_html=True)
        with st.form("finca"):
            st.markdown("**Nueva consulta**")
            claves = list(LOCALIDADES)
            localidad = st.selectbox("Localidad", claves, index=claves.index("tupungato"),
                                     format_func=lambda c: LOCALIDADES[c]["nombre"])
            perfil = st.selectbox("Perfil", list(PERFILES), format_func=PERFILES.get)
            hectareas = st.number_input("Superficie (ha)", min_value=0.0, value=10.0, step=1.0,
                                        help="No se usa en el perfil urbano")
            dias = st.slider("Días de pronóstico", 1, 16, 7)
            if st.form_submit_button("Generar plan", type="primary", width="stretch"):
                finca = (f"una finca de {PERFILES[perfil].lower()} de {hectareas:g} hectáreas"
                         if perfil != "urbano" else "la zona urbana (perfil urbano)")
                st.session_state.pendiente = (
                    f"Armame el plan de contingencia para {finca} en {LOCALIDADES[localidad]['nombre']} "
                    f"para los próximos {dias} días")

        # Lista de texto plano sobre el fondo de la barra, como en los chats de IA (ver CSS ak-lista).
        nueva = st.container(key="ak-lista-nueva")
        st.markdown('<div class="ak-etiqueta">Conversaciones</div>', unsafe_allow_html=True)
        lista = st.container(key="ak-lista-conversaciones", gap=None)
        st.divider()
        st.caption(f"Modelo: {MODELO}")
        st.caption("Este informe no reemplaza las alertas oficiales del SMN ni las indicaciones de Defensa Civil.")
    return nueva, lista


def render_conversaciones(nueva, lista) -> None:
    """Llena la lista de conversaciones de la barra lateral; va al final de la página."""
    with nueva:
        if st.button("Nueva conversación", icon=":material/edit_square:", type="tertiary",
                     disabled=not st.session_state.historial, width="stretch"):
            init_session(new_thread())
            st.rerun()
    actual = st.session_state.config["configurable"]["thread_id"]
    with lista:
        for thread_id, titulo in list_threads():
            if st.button(titulo, key=thread_id, type="tertiary", disabled=thread_id == actual,
                         width="stretch"):
                init_session(select_thread(thread_id))
                st.rerun()


def render_bienvenida() -> None:
    st.markdown("#### ¿Qué hace AnalyKid?")
    st.markdown(
        "Arma un **plan de contingencia en PDF** para una finca o zona de Mendoza: consulta El Niño, "
        "el pronóstico, el caudal del río y las alertas oficiales, evalúa el riesgo de cinco amenazas "
        "y propone medidas con cita. Escribí tu consulta, completá el formulario de la izquierda "
        "o probá un ejemplo:")
    for col, (titulo, texto) in zip(st.columns(len(EJEMPLOS)), EJEMPLOS):
        if col.button(titulo, width="stretch"):
            st.session_state.pendiente = texto
            st.rerun()


def mensaje_de_error(e: Exception) -> str:
    texto = str(e)
    if "503" in texto or "UNAVAILABLE" in texto:
        return ("El modelo está saturado (503) y el de respaldo también falló: esperá unos minutos "
                "y volvé a enviar el mensaje. La conversación se conserva.")
    if "429" in texto or "RateLimit" in type(e).__name__ or "RESOURCE_EXHAUSTED" in texto:
        return "Se alcanzó el límite del proveedor del modelo: esperá un minuto y volvé a enviar el mensaje."
    return f"El agente falló: {texto[:500]}"


# --- Página ----------------------------------------------------------------------------

if "config" not in st.session_state:
    init_session(resume_thread())

# El nombre va arriba de la barra lateral; acá, el logo con la bajada.
_logo = base64.b64encode(LOGO.read_bytes()).decode()
st.markdown(f'<div class="ak-hero"><img src="data:image/svg+xml;base64,{_logo}" alt="AnalyKid">'
            "<div><p>Planes de contingencia ante el riesgo hídrico y climático en Mendoza · El Niño 2026-2027</p></div></div>", unsafe_allow_html=True)
conversaciones = render_sidebar()

historial = st.session_state.historial
PLACEHOLDER = "Escribí tu consulta o un cambio («¿y si la finca estuviera en San Rafael?»)"


def _burbuja(texto: str) -> None:
    st.markdown(f'<div class="ak-burbuja">{html.escape(texto)}</div>', unsafe_allow_html=True)


if not historial and "pendiente" not in st.session_state:
    # Pantalla de inicio: la caja de texto va dentro del contenedor, al centro. Al enviar, el
    # pedido pasa por `pendiente` y en la vuelta siguiente la caja ya queda abajo, como en un chat.
    with st.container(key="ak-inicio"):
        render_bienvenida()
        if inicial := st.chat_input(PLACEHOLDER, key="ak-input-inicio"):
            st.session_state.pendiente = inicial
            st.rerun()
    render_conversaciones(*conversaciones)
    st.stop()

# Streamlit re-ejecuta todo el script en cada interacción: se redibuja el historial guardado.
# Las respuestas del agente van sin avatar: el resultado ocupa todo el ancho.
for n, (pregunta, eventos) in enumerate(historial, 1):
    _burbuja(pregunta)
    with st.container():
        render_turno(eventos, f"t{n}", vivo=False)

prompt = st.chat_input(PLACEHOLDER)
prompt = prompt or st.session_state.pop("pendiente", None)
if prompt:
    turno = len(historial) + 1
    _burbuja(prompt)
    with st.container():
        try:
            eventos = render_turno(stream_turn(prompt, st.session_state.config, turno), f"t{turno}", vivo=True)
        except Exception as e:
            st.error(mensaje_de_error(e))
        else:
            # Sin st.rerun(): el turno en vivo ya quedó dibujado igual que el historial. Re-ejecutar
            # acá redibujaba todo de golpe y, mientras tanto, la página mostraba huecos en blanco
            # y el recorrido plegándose a medias.
            st.session_state.historial.append((prompt, eventos))

render_conversaciones(*conversaciones)
