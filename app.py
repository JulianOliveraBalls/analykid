"""UI de Streamlit para AnalyKid.

Cada respuesta tiene tres partes: el panel de resultado (semáforo, mapa y
pestañas con los datos de las tools), el recorrido del agente (razonamiento y
cada tool en vivo) y la respuesta final. La lógica vive en agente.py; acá solo
se dibujan los eventos que emite.

Ejecutar con:  streamlit run app.py
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from tools.risk import evaluar, nivel_maximo

st.set_page_config(page_title="AnalyKid", page_icon="🌧️", layout="wide")

try:
    from agente import (
        MODELO, list_threads, new_thread, resume_thread, saved_turns, select_thread, stream_turn,
    )
except RuntimeError as e:  # por ejemplo, faltan API keys en el .env
    st.error(str(e))
    st.stop()

DIR = Path(__file__).parent
LOCALIDADES = json.loads((DIR / "datos" / "localidades.json").read_text(encoding="utf-8"))["localidades"]
RIOS = json.loads((DIR / "datos" / "rios.json").read_text(encoding="utf-8"))["rios"]
OASIS = {"norte": "Norte", "este": "Este", "valle_de_uco": "Valle de Uco", "sur": "Sur",
         "alta_montana": "Alta montaña"}
PERFILES = {"vid": "Vid", "frutal": "Frutal", "hortaliza": "Hortaliza", "urbano": "Urbano"}
EJEMPLOS = [
    ("🍇 Vid en Tupungato", "Armame el plan de contingencia para una finca de vid de 10 hectáreas "
                           "en Tupungato para los próximos 7 días"),
    ("🍑 Frutal en San Rafael", "Armame el plan de contingencia para una finca de frutales de 25 "
                               "hectáreas en San Rafael para los próximos 5 días"),
    ("🏘️ Zona urbana en Luján de Cuyo", "Armame el plan de contingencia para la zona urbana de "
                                       "Luján de Cuyo, perfil urbano, para los próximos 7 días"),
]
ICONO_NIVEL = {"verde": "🟢", "amarillo": "🟡", "naranja": "🟠", "rojo": "🔴",
               "sin datos": "⚪", "no aplica": "➖"}
TITULOS = {
    "get_enso_status": ("🌊", "Estado de El Niño (NOAA)"),
    "get_weather_forecast": ("🌦️", "Pronóstico"),
    "get_river_discharge": ("🏞️", "Caudal del río"),
    "web_search": ("🚨", "Alertas oficiales"),
    "evaluate_risk": ("🚦", "Evaluación de riesgo"),
    "search_knowledge_base": ("📚", "Base de conocimiento"),
    "load_skill": ("📖", "Skill"),
    "create_pdf": ("📄", "Informe PDF"),
}

st.markdown("""
<style>
.block-container {padding-top: 1.6rem; max-width: 1200px;}
.ak-hero {background: linear-gradient(120deg, #0E7490 0%, #155E75 60%, #164E63 100%);
  color: #fff; border-radius: 14px; padding: 18px 24px; margin-bottom: 14px;}
.ak-hero h1 {color: #fff; font-size: 1.9rem; margin: 0; padding: 0;}
.ak-hero p {margin: 4px 0 0; opacity: .9;}
.ak-card {border-radius: 12px; padding: 12px 14px; min-height: 118px; color: #fff;
  box-shadow: 0 1px 3px rgba(0,0,0,.12);}
.ak-card .ak-amenaza {font-size: .82rem; text-transform: uppercase; letter-spacing: .04em; opacity: .9;}
.ak-card .ak-nivel {font-size: 1.35rem; font-weight: 700; margin: 2px 0 4px;}
.ak-card .ak-motivo {font-size: .82rem; line-height: 1.25; opacity: .95;}
.ak-verde {background: #2E7D32;} .ak-amarillo {background: #F9A825; color: #1F2933;}
.ak-naranja {background: #EF6C00;} .ak-rojo {background: #C62828;}
.ak-sin-datos, .ak-no-aplica {background: #78909C;}
.ak-titulo {display: flex; align-items: baseline; gap: .6rem; flex-wrap: wrap; margin: 4px 0 10px;}
.ak-titulo h3 {margin: 0; padding: 0;}
.ak-chip {display: inline-block; border-radius: 999px; padding: 2px 10px; font-size: .8rem;
  background: #E6F0F3; color: #155E75;}
.ak-razonamiento {border-left: 3px solid #0E7490; background: #F0F7F9; padding: 8px 12px;
  border-radius: 0 8px 8px 0; font-style: italic; color: #334E58; margin: 4px 0 8px; font-size: .9rem;}
</style>
""", unsafe_allow_html=True)


def _dm(iso: str | None) -> str:
    return date.fromisoformat(iso[:10]).strftime("%d/%m") if iso else "s/d"


def init_session(config) -> None:
    """Carga en session_state la conversación indicada (vacía si es nueva)."""
    st.session_state.config = config
    st.session_state.historial = saved_turns(config)   # lista de (pregunta, eventos)


# --- Recorrido del agente: razonamiento y tools en vivo ---------------------------

def _titulo(e: dict) -> str:
    icono, nombre = TITULOS.get(e["nombre"], ("🔧", e["nombre"]))
    args = e["args"]
    detalle = {
        "get_weather_forecast": f"{args.get('localidad', '')}, {args.get('dias', 7)} días",
        "get_river_discharge": args.get("localidad", args.get("rio", "")),
        "evaluate_risk": f"perfil {args.get('perfil', '')}",
        "web_search": args.get("zona", ""),
        "search_knowledge_base": f"«{args.get('consulta', '')}»",
        "load_skill": args.get("nombre", ""),
        "create_pdf": f"«{args.get('titulo', '')}»",
    }.get(e["nombre"], "")
    return f"{icono} **{nombre}**" + (f" · {detalle}" if detalle else "")


def _resumen(texto: str) -> str:
    primera = texto.strip().splitlines()[0] if texto.strip() else ""
    return primera[:220] + ("…" if len(primera) > 220 else "")


class Turno:
    """Acumula lo que devolvieron las tools en un turno, para el panel de resultado."""

    def __init__(self):
        self.datos: dict[str, object] = {}       # nombre de la tool -> último artifact válido
        self.llamadas: set[str] = set()          # tools llamadas (aunque hayan fallado)
        self.fuentes: list[dict] = []
        self.textos: list[tuple[int, str]] = []  # (posición del evento, texto)
        self.ultima_llamada = -1
        self.errores = 0


def render_recorrido(eventos, turno: Turno) -> list[dict]:
    """Dibuja razonamiento y tools a medida que llegan. Devuelve los eventos dibujados."""
    emitidos, pendientes, placeholders = [], {}, {}
    for pos, e in enumerate(eventos):
        emitidos.append(e)
        tipo = e["tipo"]
        if tipo == "razonamiento":
            texto = "<br>".join(l.strip() for l in e["texto"].splitlines() if l.strip())
            st.markdown(f'<div class="ak-razonamiento">💭 {texto}</div>', unsafe_allow_html=True)
        elif tipo == "texto":
            placeholders[pos] = st.empty()
            placeholders[pos].markdown(e["texto"])
            turno.textos.append((pos, e["texto"]))
        elif tipo == "llamada":
            turno.ultima_llamada = pos
            turno.llamadas.add(e["nombre"])
            caja = st.empty()
            caja.markdown(f"⏳ {_titulo(e)}")
            pendientes[e["id"]] = (e, caja)
        elif tipo == "resultado":
            llamada, caja = pendientes.pop(e["id"])
            error = e["texto"].startswith("ERROR")
            turno.errores += error
            if not error and e["datos"]:
                turno.datos[llamada["nombre"]] = e["datos"]
            with caja.container():
                st.markdown(f"{'❌' if error else '✅'} {_titulo(llamada)}")
                st.caption(_resumen(e["texto"]))
        elif tipo == "fuentes":
            turno.fuentes = e["fuentes"]
    # La respuesta final (texto posterior a la última tool) se muestra fuera del recorrido.
    for pos, _ in turno.textos:
        if pos > turno.ultima_llamada:
            placeholders[pos].empty()
    return emitidos


# --- Panel de resultado ------------------------------------------------------------

def _tarjetas(amenazas: list[dict]) -> None:
    for col, a in zip(st.columns(len(amenazas)), amenazas):
        clase = a["nivel"].replace(" ", "-")
        col.markdown(
            f'<div class="ak-card ak-{clase}"><div class="ak-amenaza">{a["amenaza"]}</div>'
            f'<div class="ak-nivel">{a["nivel"].capitalize()}</div>'
            f'<div class="ak-motivo">{a["motivo"]}</div></div>', unsafe_allow_html=True)


def _mapa(pron: dict | None, caudal: dict | None) -> None:
    puntos = []
    if pron:
        puntos.append({"lat": pron["latitud"], "lon": pron["longitud"], "color": "#0E7490E6", "tam": 2500})
    if caudal:
        puntos.append({"lat": caudal["latitud"], "lon": caudal["longitud"], "color": "#2563EBB3", "tam": 1800})
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
    st.bar_chart(tabla.set_index("Fecha")[["Lluvia (mm)"]], height=200, color="#0E7490")
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
    st.line_chart(serie.set_index("fecha"), y_label="m³/s", height=260, color=["#0E7490", "#94A3B8"])
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
        st.error(f"🚨 **{a['titulo']}** · {a['dominio']} · {_dm(a['fecha'])}  \n{a.get('resumen', '')}  \n[Ver fuente]({a['url']})")
    for a in info:
        st.info(f"ℹ️ **{a['titulo']}** · {a['dominio']} · {_dm(a['fecha'])}  \n{a.get('resumen', '')}  \n[Ver fuente]({a['url']})")
    if d["descartados"]:
        st.caption(f"{len(d['descartados'])} resultado(s) descartado(s): otro dominio, sin fecha o de más de 48 h.")


def _tab_fuentes(turno: Turno) -> None:
    conocimiento = turno.datos.get("search_knowledge_base")
    if conocimiento:
        st.markdown("**Base de conocimiento (última consulta)**")
        for f in conocimiento:
            st.markdown(f"- 📄 **{f['documento']} — {f['seccion']}** ({f['origen']})")
    if turno.fuentes:
        st.markdown("**Todas las fuentes del turno**")
        for s in turno.fuentes:
            st.markdown(f"- [{s['title']}]({s['url']})" if s["url"].startswith("http") else f"- 📄 {s['title']}")
    if not conocimiento and not turno.fuentes:
        st.caption("Sin fuentes registradas en este turno.")


def _tab_pdf(d: dict, clave: str) -> None:
    pdf = Path(d["pdf"])
    if not pdf.exists():
        st.warning("El PDF ya no está en output/.")
        return
    try:
        st.pdf(str(pdf), height=700)
    except Exception:   # sin el componente streamlit-pdf, solo queda la descarga
        st.caption("Vista previa no disponible: descargá el PDF.")
    with st.expander("Código LaTeX generado"):
        st.code(d.get("latex", ""), language="latex")


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
        chips += [pron["oasis"], f"Río {pron['rio'].capitalize()}",
                  "Piedemonte" if pron["piedemonte"] else "Fuera del piedemonte"]
    if riesgo and riesgo.get("etapa"):
        e = riesgo["etapa"]
        chips.append(f"🍇 {e['etapa'].capitalize()}" + (" · período crítico" if e["periodo_critico"] else ""))
    chips.append(f"{ICONO_NIVEL.get(maximo, '')} Nivel máximo: {maximo}")
    st.markdown(f'<div class="ak-titulo"><h3>📍 {lugar}</h3>'
                + "".join(f'<span class="ak-chip">{c}</span>' for c in chips) + "</div>",
                unsafe_allow_html=True)
    _tarjetas(amenazas)
    if riesgo and riesgo.get("ventanas"):
        st.markdown("**Cronograma de acciones**")
        st.dataframe(pd.DataFrame([{"Amenaza": n, "Antes": v["antes"], "Durante": v["durante"],
                                    "Después": v["despues"]} for n, v in riesgo["ventanas"].items()]),
                     hide_index=True, width="stretch")
    if riesgo and riesgo.get("escalamiento"):
        with st.expander("⬆️ Qué haría subir el nivel"):
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
            st.markdown("**Contactos de emergencia**")
            cc = e.get("contingencias_climaticas")
            st.markdown(f"📞 Emergencias: **{e['general']}**" +
                        (f"  \n📞 Defensa Civil municipal: **{municipal}**" if municipal else
                         "  \n_Sin contacto municipal verificado_") +
                        (f"  \n🌾 Denuncia de daños (Contingencias Climáticas, {cc['delegacion']}): "
                         f"**{cc['telefono']}**" if cc else ""))
        if pdf and Path(pdf["pdf"]).exists():
            st.download_button("⬇️ Descargar plan (PDF)", Path(pdf["pdf"]).read_bytes(),
                               file_name=Path(pdf["pdf"]).name, mime="application/pdf",
                               key=f"{clave}-pdf", type="primary", width="stretch")

    nombres = ["🌦️ Pronóstico", "🏞️ Caudal", "🚨 Alertas", "📚 Fuentes"] + (["📄 Informe"] if pdf else [])
    tabs = st.tabs(nombres)
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
    with tabs[3]:
        _tab_fuentes(turno)
    if pdf:
        with tabs[4]:
            _tab_pdf(pdf, clave)


# --- Un turno completo ---------------------------------------------------------------

def render_turno(eventos, perfil: str | None, clave: str, vivo: bool) -> list[dict]:
    """Panel arriba, recorrido en el medio, respuesta abajo. Sirve en vivo y para el historial.

    El panel se crea primero (vacío) y se llena al final, cuando ya llegaron todos los datos.
    """
    panel = st.container()
    turno = Turno()
    recorrido = st.status("AnalyKid está trabajando…" if vivo else "Recorrido del agente",
                          expanded=vivo, state="running" if vivo else "complete")
    respuesta = st.container()
    with recorrido:
        emitidos = render_recorrido(eventos, turno)
    n = sum(e["tipo"] == "llamada" for e in emitidos)
    recorrido.update(label=f"Recorrido del agente · {n} herramienta(s)"
                     + (f" · {turno.errores} con error" if turno.errores else ""),
                     state="error" if turno.errores else "complete", expanded=False)
    with respuesta:
        for pos, texto in turno.textos:
            if pos > turno.ultima_llamada:
                st.markdown(texto)
    with panel:
        render_panel(turno, perfil, clave)
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
        st.markdown("## 🌧️ AnalyKid")
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

        st.markdown("**Conversaciones**")
        if st.button("➕ Nueva conversación", disabled=not st.session_state.historial, width="stretch"):
            init_session(new_thread())
            st.rerun()
        for thread_id, titulo in list_threads():
            if st.button(titulo, key=thread_id, disabled=thread_id == actual, width="stretch"):
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
        "y propone medidas con cita. Completá el formulario de la izquierda o probá un ejemplo:")
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

st.markdown('<div class="ak-hero"><h1>🌧️ AnalyKid</h1>'
            "<p>Planes de contingencia ante el riesgo hídrico y climático en Mendoza · El Niño 2026-2027</p></div>",
            unsafe_allow_html=True)
render_sidebar()

historial = st.session_state.historial
if not historial and "pendiente" not in st.session_state:
    render_bienvenida()

# Streamlit re-ejecuta todo el script en cada interacción: se redibuja el historial guardado.
for n, (pregunta, eventos) in enumerate(historial, 1):
    st.chat_message("user").markdown(pregunta)
    with st.chat_message("assistant", avatar="🌧️"):
        render_turno(eventos, perfil_de([p for p, _ in historial[:n]]), f"t{n}", vivo=False)

prompt = st.chat_input("Escribí tu consulta o un cambio («¿y si la finca estuviera en San Rafael?»)")
prompt = prompt or st.session_state.pop("pendiente", None)
if prompt:
    turno = len(historial) + 1
    st.chat_message("user").markdown(prompt)
    with st.chat_message("assistant", avatar="🌧️"):
        try:
            perfil = perfil_de([p for p, _ in historial] + [prompt])
            eventos = render_turno(stream_turn(prompt, st.session_state.config, turno),
                                   perfil, f"t{turno}", vivo=True)
        except Exception as e:
            st.error(mensaje_de_error(e))
            st.stop()
    st.session_state.historial.append((prompt, eventos))
    st.rerun()   # redibuja todo desde session_state
