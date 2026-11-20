"""UI de Streamlit para AnalyKid: muestra en vivo el recorrido del agente.

La lógica vive en agente.py; acá solo se dibujan los eventos que emite.

Ejecutar con:  streamlit run app.py
"""
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="AnalyKid", page_icon="🌧️")

try:
    from agente import (
        MODELO, list_threads, new_thread, resume_thread, saved_turns, select_thread, stream_turn,
    )
except RuntimeError as e:  # por ejemplo, faltan API keys en el .env
    st.error(str(e))
    st.stop()

PASOS_EXPANDIDOS = False   # resultados plegados durante el streaming (el PDF queda a la vista)
EJEMPLO = ("Armame el plan de contingencia para una finca de vid de 10 hectáreas "
           "en Tupungato para los próximos 7 días")


def init_session(config) -> None:
    """Carga en session_state la conversación indicada (vacía si es nueva)."""
    st.session_state.config = config
    st.session_state.historial = saved_turns(config)   # lista de (pregunta, eventos)


def _dm(iso: str | None) -> str:
    return date.fromisoformat(iso[:10]).strftime("%d/%m") if iso else "s/d"


# --- Títulos y detalle de cada tool -------------------------------------------

def titulo_llamada(e: dict) -> str:
    nombre, args = e["nombre"], e["args"]
    titulos = {
        "get_enso_status": lambda: "🌊 Estado de El Niño (NOAA)",
        "get_weather_forecast": lambda: f"🌦️ Pronóstico: {args.get('localidad', '')}, {args.get('dias', 7)} días",
        "get_river_discharge": lambda: f"🏞️ Caudal del río {args.get('rio', '')}",
        "web_search": lambda: f"🚨 Alertas oficiales: {args.get('zona', '')}",
        "search_knowledge_base": lambda: f"📚 Base de conocimiento: «{args.get('consulta', '')}»",
        "load_skill": lambda: f"📖 Skill «{args.get('nombre', '')}»",
        "create_pdf": lambda: f"📄 PDF: «{args.get('titulo', '')}»",
    }
    return titulos.get(nombre, lambda: f"🔧 {nombre}")()


def _enso(d: dict) -> None:
    st.metric(f"RONI {d['trimestre']}", f"{d['valor']:+.2f}",
              f"{d['fase']} {d['categoria']} · tendencia {d['tendencia']}", delta_color="off")
    st.caption(f"Dato: {d['origen']}")


def _pronostico(d: dict) -> None:
    tabla = pd.DataFrame(d["dias"]).rename(columns={
        "fecha": "Fecha", "lluvia_mm": "Lluvia (mm)", "prob_pct": "Prob. (%)", "cape_jkg": "CAPE (J/kg)",
        "rafaga_kmh": "Ráfaga (km/h)", "tmax_c": "Máx (°C)", "tmin_c": "Mín (°C)"})
    tabla["Fecha"] = tabla["Fecha"].map(_dm)
    st.dataframe(tabla, hide_index=True, width="stretch")
    i = d["indicadores"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lluvia máx.", f"{i['lluvia_max_mm']} mm", _dm(i["fecha_lluvia_max"]), delta_color="off")
    c2.metric("CAPE máx.", f"{i['cape_max_jkg']} J/kg", _dm(i["fecha_cape_max"]), delta_color="off")
    c3.metric("Días ≥ 10 mm", i["dias_lluvia_10mm"])
    c4.metric("Días hongos", i["dias_favorables_hongos"])
    e = d["emergencias"]
    municipal = e["defensa_civil_municipal"] if e.get("verificado") else "sin contacto verificado"
    st.caption(f"Emergencias: {e['general']} · Defensa Civil municipal: {municipal}")


def _caudal(d: dict) -> None:
    serie = pd.DataFrame(d["serie"]).rename(columns={
        "caudal_m3s": "Caudal previsto", "media_1991_2020_m3s": "Media 1991-2020"})
    serie["fecha"] = pd.to_datetime(serie["fecha"])
    st.line_chart(serie.set_index("fecha"), y_label="m³/s")
    st.metric("Cociente máximo / media", d["cociente"],
              f"máx. {d['caudal_max_m3s']} m³/s el {_dm(d['fecha_max'])}", delta_color="off")


def _alertas(d: dict) -> None:
    if d.get("zona_usada"):
        st.caption(f"Búsqueda: {d['zona_usada']}")
    for a in d["elegidos"]:
        tipo = "🚨 Alerta" if a.get("es_alerta") else "ℹ️ Información oficial"
        st.markdown(f"- {tipo} · **{_dm(a['fecha'])}** · {a['dominio']} · [{a['titulo']}]({a['url']})")
    if not d["elegidos"]:
        st.markdown("Sin alertas oficiales en las últimas 48 h.")
    if d["descartados"]:
        with st.expander(f"Descartados ({len(d['descartados'])})"):
            for x in d["descartados"]:
                st.markdown(f"- {x['url']} · fecha: {x['fecha'] or 'sin fecha'}")


def _conocimiento(d: list) -> None:
    for f in d:
        st.markdown(f"- 📄 **{f['documento']} — {f['seccion']}** ({f['origen']}): _{f['fragmento']}…_")


DETALLES = {
    "get_enso_status": _enso, "get_weather_forecast": _pronostico, "get_river_discharge": _caudal,
    "web_search": _alertas, "search_knowledge_base": _conocimiento,
}


def detalle_resultado(llamada: dict, r: dict) -> str:
    """Dibuja lo que devolvió la tool dentro de su st.status. Devuelve el estado final."""
    if r["texto"].startswith("ERROR"):
        st.error(r["texto"])
        return "error"
    nombre, datos = llamada["nombre"], r["datos"]
    if nombre in DETALLES and datos:
        DETALLES[nombre](datos)
    elif nombre == "load_skill":
        st.caption(f"{len(r['texto'])} caracteres cargados")
    elif nombre == "create_pdf" and datos:
        st.code(datos["latex"], language="latex")
    else:
        st.text(r["texto"])
    return "complete"


def boton_pdf(r: dict) -> None:
    """El PDF queda fuera del st.status plegado, siempre a la vista."""
    pdf = Path(r["datos"]["pdf"])
    if pdf.exists():
        st.download_button(f"⬇️ Descargar {pdf.name}", pdf.read_bytes(), file_name=pdf.name,
                           mime="application/pdf", key=r["id"], type="primary")


# --- Eventos --------------------------------------------------------------------

def render_eventos(eventos) -> list[dict]:
    """Dibuja los eventos a medida que llegan; sirve en vivo (generador) y para el historial (lista).

    Devuelve los eventos ya dibujados, para guardarlos en el historial.
    """
    emitidos = []
    llamadas = {}   # id del tool call -> (evento de la llamada, contenedor st.status)
    for e in eventos:
        emitidos.append(e)
        tipo = e["tipo"]
        if tipo == "razonamiento":
            with st.expander("💭 Razonamiento", expanded=PASOS_EXPANDIDOS):
                # Un salto de línea por renglón y sin sangrías (que markdown tomaría por código).
                st.markdown("  \n".join(l.strip() for l in e["texto"].splitlines()))
        elif tipo == "texto":
            st.markdown(e["texto"])
        elif tipo == "llamada":
            # Queda en "running" hasta que llega el resultado; las llamadas en paralelo aparecen juntas.
            status = st.status(titulo_llamada(e), expanded=PASOS_EXPANDIDOS)
            with status:
                st.caption(" · ".join(f"{k}={v}" for k, v in e["args"].items() if k != "cuerpo"))
            llamadas[e["id"]] = (e, status)
        elif tipo == "resultado":
            llamada, status = llamadas[e["id"]]
            with status:
                estado = detalle_resultado(llamada, e)
            status.update(state=estado)
            if llamada["nombre"] == "create_pdf" and estado == "complete" and e["datos"]:
                boton_pdf(e)
        elif tipo == "fuentes":
            with st.expander(f"Fuentes consultadas ({len(e['fuentes'])})"):
                for s in e["fuentes"]:
                    if s["url"].startswith("http"):
                        st.markdown(f"- [{s['title']}]({s['url']})")
                    else:
                        st.markdown(f"- 📄 {s['title']}")
    return emitidos


def render_sidebar() -> None:
    """Conversaciones (nueva y anteriores) y modelo activo."""
    actual = st.session_state.config["configurable"]["thread_id"]
    with st.sidebar:
        st.header("Conversaciones")
        # Deshabilitado si la actual todavía está vacía: no tiene sentido crear otra.
        if st.button("➕ Nueva conversación", disabled=not st.session_state.historial):
            init_session(new_thread())
            st.rerun()
        for thread_id, titulo in list_threads():
            if st.button(titulo, key=thread_id, disabled=thread_id == actual,
                         width="stretch"):
                init_session(select_thread(thread_id))
                st.rerun()
        st.divider()
        st.caption(f"Modelo: {MODELO}")


def mensaje_de_error(e: Exception) -> str:
    texto = str(e)
    if "429" in texto or "RateLimit" in type(e).__name__ or "RESOURCE_EXHAUSTED" in texto:
        return "Se alcanzó el límite del proveedor del modelo: esperá un minuto y volvé a enviar el mensaje."
    if "503" in texto or "UNAVAILABLE" in texto:
        return ("El modelo está saturado (503) y el de respaldo también falló: esperá unos minutos "
                "y volvé a enviar el mensaje. La conversación se conserva.")
    return f"El agente falló: {texto[:500]}"


if "config" not in st.session_state:
    init_session(resume_thread())

st.title("🌧️ AnalyKid")
st.caption("Planes de contingencia ante el riesgo hídrico y climático en Mendoza · El Niño 2026-2027")
render_sidebar()

# Streamlit re-ejecuta todo el script en cada interacción: se redibuja el historial guardado.
for pregunta, eventos in st.session_state.historial:
    st.chat_message("user").markdown(pregunta)
    with st.chat_message("assistant"):
        render_eventos(eventos)

if prompt := st.chat_input(EJEMPLO):
    turno = len(st.session_state.historial) + 1
    st.chat_message("user").markdown(prompt)
    with st.chat_message("assistant"):
        try:
            with st.spinner("AnalyKid está trabajando..."):
                eventos = render_eventos(stream_turn(prompt, st.session_state.config, turno))
        except Exception as e:
            st.error(mensaje_de_error(e))
            st.stop()

    st.session_state.historial.append((prompt, eventos))
    st.rerun()   # redibuja todo desde session_state
