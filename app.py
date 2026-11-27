"""UI de Streamlit para AnalyKid.

Cada respuesta tiene tres partes: el panel de resultado (semáforo, mapa y
pestañas con los datos de las tools), la respuesta final y el recorrido del
agente, paso a paso: en cada paso se ve la cadena de pensamiento del modelo y,
por cada tool, la invocación, los parámetros que le pasó y el resultado que
recibió. La lógica vive en agente.py; acá solo se dibujan los eventos que emite.

Ejecutar con:  streamlit run app.py
"""
import base64
import html
import json
import os
import re
from datetime import date
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from tools.risk import evaluar, nivel_maximo

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
RIOS = json.loads((DIR / "datos" / "rios.json").read_text(encoding="utf-8"))["rios"]
OASIS = {"norte": "Norte", "este": "Este", "valle_de_uco": "Valle de Uco", "sur": "Sur",
         "alta_montana": "Alta montaña"}
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

# Marca: blanco, texto oscuro y el azul solo en detalles. Los únicos colores fuera de la
# paleta son los del semáforo.
NAVY, AZUL, GRIS = "#0B1F5C", "#1226B4", "#6B7280"

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


def _dm(iso: str | None) -> str:
    return date.fromisoformat(iso[:10]).strftime("%d/%m") if iso else "s/d"


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


class Paso:
    """Un paso del ciclo del agente: lo que el modelo pensó y las tools que pidió en esa respuesta.

    Las tools de un mismo paso se piden juntas (en paralelo); el paso se cierra cuando el
    modelo vuelve a responder.
    """

    def __init__(self, n: int, vivo: bool):
        self.n = n
        self.nombres: list[str] = []
        self.errores = 0
        self.con_pensamiento = False
        # Abierto mientras el agente trabaja (la consigna pide ver cada tool en vivo); en el
        # historial queda plegado y se abre a demanda, como el razonamiento de un chat.
        self.caja = st.status(f"Paso {n}", expanded=vivo, state="running" if vivo else "complete")

    def pensamiento(self) -> None:
        """Encabezado de la cadena de pensamiento, una sola vez por paso."""
        if not self.con_pensamiento:
            _etiqueta("Cadena de pensamiento")
            self.con_pensamiento = True

    def cerrar(self) -> None:
        if self.nombres:
            detalle = ", ".join(dict.fromkeys(self.nombres))
            if len(self.nombres) > 1:
                detalle += f" ({len(self.nombres)} llamadas en paralelo)"
        else:
            detalle = "respuesta del modelo, sin tools"
        if self.errores:
            detalle += f" · {self.errores} con error"
        self.caja.update(label=f"Paso {self.n} · {detalle}",
                         state="error" if self.errores else "complete")


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


def render_recorrido(eventos, turno: Turno, vivo: bool) -> list[dict]:
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
            paso = Paso(turno.pasos, vivo)
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


# --- Panel de resultado ------------------------------------------------------------

def _tarjetas(amenazas: list[dict]) -> None:
    for col, a in zip(st.columns(len(amenazas)), amenazas):
        clase = a["nivel"].replace(" ", "-")
        col.markdown(
            f'<div class="ak-card ak-{clase}"><div class="ak-amenaza">{a["amenaza"]}</div>'
            f'<div class="ak-nivel"><span class="ak-punto"></span>{a["nivel"].capitalize()}</div>'
            f'<div class="ak-motivo">{a["motivo"]}</div></div>', unsafe_allow_html=True)


def _mapa(pron: dict | None, caudal: dict | None) -> None:
    puntos = []
    if pron:
        puntos.append({"lat": pron["latitud"], "lon": pron["longitud"], "color": NAVY + "E6", "tam": 2500})
    if caudal:
        puntos.append({"lat": caudal["latitud"], "lon": caudal["longitud"], "color": AZUL + "99", "tam": 1800})
    if puntos:
        st.map(pd.DataFrame(puntos), latitude="lat", longitude="lon", color="color", size="tam",
               zoom=8, height=290)
        st.caption("Punto grande: localidad · punto chico: punto de consulta del río (GloFAS)")


def _tab_pronostico(d: dict, riesgo: dict | None) -> None:
    if riesgo and riesgo.get("dias_criticos"):
        st.markdown("**Días críticos**")
        for c in riesgo["dias_criticos"]:
            st.markdown(f"- **{_dm(c['fecha'])}**: {', '.join(c['motivos'])}")
    tabla = pd.DataFrame(d["dias"]).rename(columns={
        "fecha": "Fecha", "lluvia_mm": "Lluvia (mm)", "prob_pct": "Prob. (%)", "cape_jkg": "CAPE (J/kg)",
        "rafaga_kmh": "Ráfaga (km/h)", "tmax_c": "Máx (°C)", "tmin_c": "Mín (°C)"})
    tabla["Fecha"] = tabla["Fecha"].map(_dm)
    # Altair y no st.bar_chart: con el índice de texto las fechas se ordenaban como texto (01/12
    # antes que 26/11) y la barra más alta quedaba cortada arriba.
    barras = alt.Chart(tabla).mark_bar(color=AZUL, cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        x=alt.X("Fecha:N", sort=None, axis=alt.Axis(labelAngle=0, title=None)),
        y=alt.Y("Lluvia (mm):Q", scale=alt.Scale(domainMin=0, nice=True, padding=12)),
        tooltip=["Fecha", "Lluvia (mm)", "Prob. (%)"])
    valores = barras.mark_text(dy=-7, color=NAVY, fontSize=11).encode(
        text=alt.Text("Lluvia (mm):Q", format=".1f"))
    st.altair_chart((barras + valores).properties(height=240), width="stretch")
    st.dataframe(tabla, hide_index=True, width="stretch")
    i = d["indicadores"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lluvia acumulada", f"{i['lluvia_acumulada_mm']} mm")
    c2.metric("Ráfaga máx.", f"{i['rafaga_max_kmh']} km/h", _dm(i["fecha_rafaga_max"]), delta_color="off", delta_arrow="off")
    c3.metric("Días ≥ 10 mm", i["dias_lluvia_10mm"])
    c4.metric("Mínima más baja", f"{i['tmin_mas_baja_c']} °C", _dm(i["fecha_tmin_mas_baja"]), delta_color="off", delta_arrow="off")


def _tab_caudal(d: dict) -> None:
    serie = pd.DataFrame(d["serie"]).rename(columns={
        "caudal_m3s": "Caudal previsto", "media_1991_2020_m3s": "Media 1991-2020"})
    serie["fecha"] = pd.to_datetime(serie["fecha"])
    st.line_chart(serie.set_index("fecha"), y_label="m³/s", height=260, color=[AZUL, GRIS])
    c1, c2, c3 = st.columns(3)
    c1.metric("Cociente máx. / media", d["cociente"])
    c2.metric("Caudal máx.", f"{d['caudal_max_m3s']} m³/s", _dm(d["fecha_max"]), delta_color="off", delta_arrow="off")
    c3.metric("Tendencia", d["tendencia"].capitalize())
    st.caption(f"{d['nombre']} en {d['estacion']}. Caudal simulado (GloFAS): no incluye la regulación de los embalses.")


def _tab_alertas(d: dict | None, llamada: bool) -> None:
    if d is None:
        st.info("La búsqueda de alertas falló: el informe sigue sin alertas oficiales." if llamada
                else "No se consultaron alertas en este turno.")
        return
    if d.get("zona_usada"):
        st.caption(f"Búsqueda: {d['zona_usada']} · dominios oficiales · últimas 48 h")
    alertas = [a for a in d["elegidos"] if a.get("es_alerta")]
    info = [a for a in d["elegidos"] if not a.get("es_alerta")]
    if not alertas:
        st.success("Sin alertas oficiales vigentes. No implica ausencia de riesgo.")
    for a in alertas:
        st.error(f"**Alerta oficial · {a['titulo']}** · {a['dominio']} · {_dm(a['fecha'])}  \n{a.get('resumen', '')}  \n[Ver fuente]({a['url']})")
    for a in info:
        st.info(f"**Información oficial · {a['titulo']}** · {a['dominio']} · {_dm(a['fecha'])}  \n{a.get('resumen', '')}  \n[Ver fuente]({a['url']})")
    if d["descartados"]:
        st.caption(f"{len(d['descartados'])} resultado(s) descartado(s): otro dominio, sin fecha o de más de 48 h.")


def _completar_pronostico(d: dict | None) -> dict | None:
    """Conversaciones guardadas con una versión anterior de la tool no traen estos campos:
    se completan desde el catálogo."""
    if not d or d.get("localidad") not in LOCALIDADES:
        return d
    loc = LOCALIDADES[d["localidad"]]
    return {"nombre": loc["nombre"], "departamento": loc["departamento"],
            "oasis": OASIS.get(loc["oasis"], loc["oasis"]), "piedemonte": loc["piedemonte"],
            "rio": loc["rio"], "latitud": loc["latitud"], "longitud": loc["longitud"],
            "emergencias": loc["emergencias"], **d}


def _completar_caudal(d: dict | None) -> dict | None:
    if not d or d.get("rio") not in RIOS:
        return d
    r = RIOS[d["rio"]]
    return {"nombre": r["nombre"], "estacion": r["estacion_referencia"],
            "latitud": r["consulta"]["latitud"], "longitud": r["consulta"]["longitud"], **d}


def render_panel(turno: Turno, perfil: str | None, clave: str) -> None:
    pron = _completar_pronostico(turno.datos.get("get_weather_forecast"))
    caudal = _completar_caudal(turno.datos.get("get_river_discharge"))
    enso = turno.datos.get("get_enso_status")
    pdf = turno.datos.get("create_pdf")
    if not (pron or caudal or pdf):
        return

    riesgo = turno.datos.get("evaluate_risk")
    if riesgo:   # el mismo cálculo que recibe el modelo y verifica create_pdf
        amenazas, maximo = riesgo["amenazas"], riesgo["nivel_maximo"]
    else:        # conversaciones guardadas antes de evaluate_risk
        amenazas = evaluar(pron, caudal, perfil)
        maximo = nivel_maximo(amenazas)
    lugar = pron["nombre"] if pron else (caudal["nombre"] if caudal else "Resultado")
    chips = []
    if pron:
        chips += [pron["oasis"], RIOS.get(pron["rio"], {}).get("nombre", f"Río {pron['rio'].capitalize()}"),
                  "Piedemonte" if pron["piedemonte"] else "Fuera del piedemonte"]
    if riesgo and riesgo.get("etapa"):
        e = riesgo["etapa"]
        chips.append(f"Etapa: {e['etapa']}" + (" · período crítico" if e["periodo_critico"] else ""))
    chips.append(f'<span class="ak-punto ak-{maximo.replace(" ", "-")}"></span>Nivel máximo: {maximo}')
    st.markdown(f'<div class="ak-titulo"><h3>{lugar}</h3>'
                + "".join(f'<span class="ak-chip">{c}</span>' for c in chips) + "</div>",
                unsafe_allow_html=True)
    _tarjetas(amenazas)
    if riesgo and riesgo.get("ventanas"):
        _seccion("Cronograma de acciones")
        st.dataframe(pd.DataFrame([{"Amenaza": n, "Antes": v["antes"], "Durante": v["durante"],
                                    "Después": v["despues"]} for n, v in riesgo["ventanas"].items()]),
                     hide_index=True, width="stretch")
    elif riesgo and riesgo.get("vigilancia"):
        st.info("Ninguna amenaza activa: no hay medidas obligatorias esta semana. "
                "Queda en vigilancia; abajo, qué haría subir el nivel.", icon="🟢")
    if riesgo and riesgo.get("escalamiento"):
        with st.expander("Qué haría subir el nivel"):
            for regla in riesgo["escalamiento"]:
                st.markdown(f"- {regla}")

    izq, der = st.columns([3, 2])
    with izq:
        _mapa(pron, caudal)
    with der:
        if enso:
            st.metric(f"El Niño · RONI {enso['trimestre']}", f"{enso['valor']:+.2f}",
                      f"{enso['fase']} {enso['categoria']} · {enso['tendencia']}", delta_color="off", delta_arrow="off")
        if pron:
            e = pron["emergencias"]
            municipal = e["defensa_civil_municipal"] if e.get("verificado") else None
            _seccion("Contactos de emergencia")
            cc = e.get("contingencias_climaticas")
            st.markdown(f"Emergencias: **{e['general']}**" +
                        (f"  \nDefensa Civil municipal: **{municipal}**" if municipal else
                         "  \n_Sin contacto municipal verificado_") +
                        (f"  \nDenuncia de daños (Contingencias Climáticas, {cc['delegacion']}): "
                         f"**{cc['telefono']}**" if cc else ""))
        if pdf and Path(pdf["pdf"]).exists():
            st.download_button("Descargar plan (PDF)", Path(pdf["pdf"]).read_bytes(),
                               file_name=Path(pdf["pdf"]).name, mime="application/pdf",
                               key=f"{clave}-pdf", type="primary", width="stretch")

    # Sin pestañas de Fuentes ni de Informe: el PDF se baja con el botón del panel.
    tabs = st.tabs(["Pronóstico", "Caudal", "Alertas"])
    with tabs[0]:
        if pron:
            _tab_pronostico(pron, riesgo)
        else:
            st.info("Sin pronóstico en este turno.")
    with tabs[1]:
        if caudal:
            _tab_caudal(caudal)
        else:
            st.info("Sin caudal en este turno.")
    with tabs[2]:
        _tab_alertas(turno.datos.get("web_search"), "web_search" in turno.llamadas)


# --- Un turno completo ---------------------------------------------------------------

def render_turno(eventos, perfil: str | None, clave: str, vivo: bool) -> list[dict]:
    """Recorrido plegado arriba y, debajo, el panel y la respuesta final. Sirve en vivo y para el historial.

    Mientras el agente trabaja, «Armando plan de contingencia…» queda abierto y cada paso se ve
    en vivo con sus tools, parámetros y resultados. Al terminar, la página se redibuja desde el
    historial: el recorrido queda plegado arriba, con su resumen, y el resultado debajo.
    """
    turno = Turno()
    with st.container(key=f"ak-recorrido-{clave}"):
        caja = st.status("Armando plan de contingencia…", expanded=vivo,
                         state="running" if vivo else "complete")
        with caja:
            st.caption("Cada paso es una respuesta del modelo: su cadena de pensamiento y, por cada "
                       "tool, la invocación, los parámetros y el resultado.")
            emitidos = render_recorrido(eventos, turno, vivo)
        n = sum(e["tipo"] == "llamada" for e in emitidos)
        caja.update(label=f"Recorrido del agente · {turno.pasos} paso(s) · {n} llamada(s) a tools"
                    + (f" · {turno.errores} con error" if turno.errores else ""), state="complete")
    render_panel(turno, perfil, clave)
    if finales := [texto for pos, texto in turno.textos if pos > turno.ultima_llamada]:
        _seccion("Respuesta final")
        for texto in finales:
            st.markdown(texto)
    return emitidos


def perfil_de(preguntas: list[str]) -> str | None:
    """Perfil mencionado en la conversación (el último que aparezca)."""
    perfil = None
    for p in preguntas:
        for clave in PERFILES:
            if clave in p.lower():
                perfil = clave
    return perfil


# --- Barra lateral --------------------------------------------------------------------

def render_sidebar() -> None:
    actual = st.session_state.config["configurable"]["thread_id"]
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
        with st.container(key="ak-lista-nueva"):
            if st.button("Nueva conversación", icon=":material/edit_square:", type="tertiary",
                         disabled=not st.session_state.historial, width="stretch"):
                init_session(new_thread())
                st.rerun()
        st.markdown('<div class="ak-etiqueta">Conversaciones</div>', unsafe_allow_html=True)
        with st.container(key="ak-lista-conversaciones", gap=None):
            for thread_id, titulo in list_threads():
                if st.button(titulo, key=thread_id, type="tertiary", disabled=thread_id == actual,
                             width="stretch"):
                    init_session(select_thread(thread_id))
                    st.rerun()
        st.divider()
        st.caption(f"Modelo: {MODELO}")
        st.caption("Este informe no reemplaza las alertas oficiales del SMN ni las indicaciones de Defensa Civil.")


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
render_sidebar()

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
    st.stop()

# Streamlit re-ejecuta todo el script en cada interacción: se redibuja el historial guardado.
# Las respuestas del agente van sin avatar: el resultado ocupa todo el ancho.
for n, (pregunta, eventos) in enumerate(historial, 1):
    _burbuja(pregunta)
    with st.container():
        render_turno(eventos, perfil_de([p for p, _ in historial[:n]]), f"t{n}", vivo=False)

prompt = st.chat_input(PLACEHOLDER)
prompt = prompt or st.session_state.pop("pendiente", None)
if prompt:
    turno = len(historial) + 1
    _burbuja(prompt)
    with st.container():
        try:
            perfil = perfil_de([p for p, _ in historial] + [prompt])
            eventos = render_turno(stream_turn(prompt, st.session_state.config, turno),
                                   perfil, f"t{turno}", vivo=True)
        except Exception as e:
            st.error(mensaje_de_error(e))
            st.stop()
    st.session_state.historial.append((prompt, eventos))
    st.rerun()   # redibuja todo desde session_state
