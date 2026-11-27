"""Panel del PDF: la primera página con los datos que ya trajeron las tools, armada en código.

El informe que escribe el modelo va después. El panel no lo escribe el modelo: sale de los
artifacts del turno (pronóstico, caudal, El Niño, alertas y evaluate_risk), así que los números
son los mismos que vio la interfaz y no gastan tokens. Todo texto externo se escapa.
"""
from datetime import date

NIVELES = {   # nivel -> (color de relleno, color de texto, rótulo)
    "verde": ("nverde", "tverde", "VERDE"),
    "amarillo": ("namarillo", "tamarillo", "AMARILLO"),
    "naranja": ("nnaranja", "tnaranja", "NARANJA"),
    "rojo": ("nrojo", "trojo", "ROJO"),
    "sin datos": ("nsindatos", "tsindatos", "SIN DATOS"),
    "no aplica": ("nsindatos", "tsindatos", "NO APLICA"),
}
_ESPECIALES = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
               "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def escapar(texto) -> str:
    """Texto plano a LaTeX: escapa los caracteres especiales."""
    return str(texto).translate(str.maketrans(_ESPECIALES))


def _dm(iso: str | None) -> str:
    return date.fromisoformat(iso[:10]).strftime("%d/%m") if iso else "s/d"


def _num(valor, decimales: int = 1) -> str:
    return f"{valor:.{decimales}f}".replace(".", ",") if isinstance(valor, (int, float)) else "s/d"


def _nivel(nivel: str) -> tuple[str, str, str]:
    return NIVELES.get(nivel, NIVELES["sin datos"])


def _encabezado(pron: dict | None, riesgo: dict | None, enso: dict | None, caudal: dict | None) -> str:
    datos = []
    if pron:
        rio = (caudal or {}).get("nombre") or f"Río {str(pron.get('rio', '')).capitalize()}"
        datos += [pron.get("oasis"), rio,
                  "Piedemonte" if pron.get("piedemonte") else "Fuera del piedemonte"]
        dias = pron.get("dias") or []
        if dias:
            datos.append(f"{_dm(dias[0]['fecha'])} al {_dm(dias[-1]['fecha'])}")
    if riesgo and riesgo.get("etapa"):
        e = riesgo["etapa"]
        datos.append(f"Etapa: {e['etapa']}" + (" (período crítico)" if e.get("periodo_critico") else ""))
    if enso:
        signo = "+" if enso["valor"] > 0 else ""
        datos.append(f"{enso['fase']} {enso['categoria']} {signo}{_num(enso['valor'], 2)}")
    linea = r" \enspace·\enspace ".join(escapar(d) for d in datos if d)
    maximo = riesgo.get("nivel_maximo", "sin datos") if riesgo else "sin datos"
    relleno, _, rotulo = _nivel(maximo)
    lugar = escapar(pron["nombre"]) if pron else "Resultado"
    return (
        "\\noindent\\begin{tikzpicture}\n"
        "\\node[fill=fondo, rounded corners=6pt, inner sep=12pt, anchor=north west, "
        "text width=\\dimexpr\\textwidth-24pt\\relax, align=left] at (0,0) {"
        f"{{\\color{{gris}}\\scriptsize\\bfseries PANEL DE DATOS}}\\\\[3pt]"
        f"{{\\color{{navy}}\\huge\\bfseries {lugar}}}\\\\[5pt]"
        f"{{\\color{{tinta}}\\small {linea}}}}};\n"
        f"\\node[fill={relleno}, rounded corners=10pt, inner sep=6pt, anchor=north east, "
        f"font=\\small\\bfseries, text={'black' if maximo == 'amarillo' else 'white'}] at (\\textwidth,-12pt) "
        f"{{Nivel máximo: {rotulo}}};\n"
        "\\end{tikzpicture}\n\n\\medskip\n"
    )


def _tarjetas(amenazas: list[dict]) -> str:
    ancho, sep = 3.18, 0.17
    partes = ["\\noindent\\begin{tikzpicture}"]
    for i, a in enumerate(amenazas[:5]):
        x = i * (ancho + sep)
        relleno, texto, rotulo = _nivel(a.get("nivel", "sin datos"))
        motivo = escapar(a.get("motivo", ""))
        if len(motivo) > 95:
            motivo = motivo[:92].rstrip() + "…"
        partes += [
            f"\\fill[fondo, rounded corners=4pt] ({x:.2f},0) rectangle ({x + ancho:.2f},-3.75);",
            f"\\fill[{relleno}] ({x:.2f},0) rectangle ({x + ancho:.2f},-0.22);",
            f"\\node[anchor=north west, text width={ancho - 0.36:.2f}cm, align=left, inner sep=0pt] at ({x + 0.18:.2f},-0.42) "
            f"{{{{\\scriptsize\\bfseries\\color{{gris}} {escapar(a.get('amenaza', '')).upper()}}}\\\\[3pt]"
            f"{{\\large\\bfseries\\color{{{texto}}} {rotulo}}}\\\\[4pt]"
            f"{{\\scriptsize\\color{{tinta}} {motivo}}}}};",
        ]
    partes.append("\\end{tikzpicture}\n\n\\medskip\n")
    return "\n".join(partes)


def _grafico_lluvia(dias: list[dict]) -> str:
    if not dias:
        return ""
    n = len(dias)
    alto, ancho = 2.3, 9.2
    paso = ancho / n
    tope = max(10.0, max(d.get("lluvia_mm") or 0 for d in dias))
    tope = 5 * (int(tope / 5) + 1)
    partes = ["\\begin{tikzpicture}",
              f"\\draw[hilo] (0,0) -- ({ancho:.2f},0);",
              f"\\node[anchor=south west, font=\\tiny\\color{{gris}}, inner sep=0pt] at (0,{alto + 0.12:.2f}) {{mm (máx. del gráfico {tope})}};"]
    for i, d in enumerate(dias):
        mm = d.get("lluvia_mm") or 0
        h = alto * mm / tope
        x = i * paso + paso * 0.18
        color = "azul" if mm >= 10 else "cielo"
        if h > 0:
            partes.append(f"\\fill[{color}, rounded corners=1.5pt] ({x:.2f},0) rectangle ({x + paso * 0.64:.2f},{h:.2f});")
        partes.append(f"\\node[font=\\tiny, anchor=south] at ({x + paso * 0.32:.2f},{h + 0.03:.2f}) {{{_num(mm)}}};")
        partes.append(f"\\node[font=\\tiny\\color{{gris}}, anchor=north] at ({x + paso * 0.32:.2f},-0.05) {{{_dm(d['fecha'])}}};")
    partes.append("\\end{tikzpicture}")
    return "\n".join(partes)


def _indicadores(ind: dict | None) -> str:
    if not ind:
        return ""
    filas = [("Lluvia acumulada", f"{_num(ind.get('lluvia_acumulada_mm'))} mm"),
             ("Lluvia máxima", f"{_num(ind.get('lluvia_max_mm'))} mm · {_dm(ind.get('fecha_lluvia_max'))}"),
             ("CAPE máximo", f"{_num(ind.get('cape_max_jkg'), 0)} J/kg · {_dm(ind.get('fecha_cape_max'))}"),
             ("Ráfaga máxima", f"{_num(ind.get('rafaga_max_kmh'), 0)} km/h · {_dm(ind.get('fecha_rafaga_max'))}"),
             ("Mínima más baja", f"{_num(ind.get('tmin_mas_baja_c'))} °C · {_dm(ind.get('fecha_tmin_mas_baja'))}"),
             ("Días favorables a hongos", str(ind.get("dias_favorables_hongos", "s/d")))]
    cuerpo = "\n".join(f"{{\\color{{gris}}\\footnotesize {escapar(k)}}} & {{\\small\\bfseries\\color{{navy}} {escapar(v)}}} \\\\"
                       for k, v in filas)
    return ("\\renewcommand{\\arraystretch}{1.35}\\begin{tabular}{@{}l@{\\hspace{8pt}}l@{}}\n" + cuerpo
            + "\n\\end{tabular}\\renewcommand{\\arraystretch}{1}")


def _cronograma(ventanas: dict, amenazas: list[dict]) -> str:
    if not ventanas:
        return ""
    niveles = {a["amenaza"]: a.get("nivel", "sin datos") for a in amenazas}
    filas = []
    for nombre, v in ventanas.items():
        relleno = _nivel(niveles.get(nombre, "sin datos"))[0]
        filas.append(f"\\textcolor{{{relleno}}}{{\\Large$\\bullet$}}\\ \\textbf{{{escapar(nombre)}}} & "
                     f"{escapar(v['antes'])} & {escapar(v['durante'])} & {escapar(v['despues'])} \\\\")
    return ("\\noindent{\\color{navy}\\bfseries Cronograma de acciones}\\par\\smallskip\n"
            "\\noindent\\renewcommand{\\arraystretch}{1.15}"
            "\\begin{tabular}{@{}>{\\raggedright\\arraybackslash}p{4.0cm}>{\\raggedright\\arraybackslash}p{3.3cm}"
            ">{\\raggedright\\arraybackslash}p{4.9cm}>{\\raggedright\\arraybackslash}p{3.3cm}@{}}\n\\toprule\n"
            "\\footnotesize\\color{gris}Amenaza & \\footnotesize\\color{gris}Antes & \\footnotesize\\color{gris}Durante "
            "& \\footnotesize\\color{gris}Después \\\\\n\\midrule\n" + "\n".join(filas)
            + "\n\\bottomrule\n\\end{tabular}\\renewcommand{\\arraystretch}{1}\n\n\\medskip\n")


def _caudal(c: dict | None) -> str:
    if not c:
        return ""
    serie = c.get("serie") or []
    resumen = (f"{{\\color{{navy}}\\bfseries {escapar(c.get('nombre', 'Río'))}}}\\\\[2pt]"
               f"{{\\small Máximo previsto {_num(c.get('caudal_max_m3s'))} m³/s el {_dm(c.get('fecha_max'))}; "
               f"media 1991-2020: {_num(c.get('media_1991_2020_m3s'))} m³/s. Cociente {_num(c.get('cociente'), 2)}, "
               f"tendencia {escapar(c.get('tendencia', 's/d'))}. Simulado (GloFAS), sin embalses.}}")
    if len(serie) < 2:
        return resumen
    valores = [p.get("caudal_m3s") or 0 for p in serie] + [p.get("media_1991_2020_m3s") or 0 for p in serie]
    piso, tope = min(valores) * 0.9, max(valores) * 1.1   # entre el mínimo y el máximo: se ve la variación
    rango = (tope - piso) or 1
    ancho, alto = 6.4, 1.1
    paso = ancho / (len(serie) - 1)
    linea = lambda clave: " -- ".join(f"({i * paso:.2f},{alto * ((p.get(clave) or 0) - piso) / rango:.2f})"
                                      for i, p in enumerate(serie))
    grafico = ("\\begin{tikzpicture}"
               f"\\draw[hilo] (0,0) -- ({ancho:.2f},0);"
               f"\\draw[gris, dashed, thick] {linea('media_1991_2020_m3s')};"
               f"\\draw[azul, very thick] {linea('caudal_m3s')};"
               f"\\node[font=\\tiny\\color{{gris}}, anchor=north west, inner sep=0pt] at (0,-0.08) {{{_dm(serie[0]['fecha'])}}};"
               f"\\node[font=\\tiny\\color{{gris}}, anchor=north east, inner sep=0pt] at ({ancho:.2f},-0.08) {{{_dm(serie[-1]['fecha'])}}};"
               f"\\node[font=\\tiny\\color{{azul}}, anchor=south west, inner sep=0pt] at (0,{alto + 0.05:.2f}) {{caudal}};"
               f"\\node[font=\\tiny\\color{{gris}}, anchor=south west, inner sep=0pt] at (1.2,{alto + 0.05:.2f}) {{media 1991-2020}};"
               "\\end{tikzpicture}")
    return resumen + "\\par\\smallskip\n" + grafico


def _alertas(web: dict | None) -> str:
    if web is None:
        return "{\\small Sin consulta de alertas en este turno.}"
    elegidos = web.get("elegidos") or []
    if not elegidos:
        return "{\\small Sin alertas oficiales vigentes encontradas. No implica ausencia de riesgo.}"
    items = []
    for a in elegidos[:4]:
        titulo = a.get("titulo") or "Aviso oficial"
        titulo = escapar(titulo if len(titulo) <= 120 else titulo[:117] + "…")
        tipo = "\\textbf{ALERTA}" if a.get("es_alerta") else "Información oficial"
        items.append(f"\\item {{\\small {tipo} · {escapar(a.get('dominio', ''))}: {titulo}}}")
    return "\\begin{itemize}\\setlength{\\itemsep}{1pt}\n" + "\n".join(items) + "\n\\end{itemize}"


def _contactos(pron: dict | None) -> str:
    e = (pron or {}).get("emergencias") or {}
    if not e:
        return ""
    lineas = [f"Emergencias: \\textbf{{{escapar(e.get('general', '911'))}}}"]
    if e.get("defensa_civil_municipal") and e.get("verificado"):
        lineas.append(f"Defensa Civil municipal: \\textbf{{{escapar(e['defensa_civil_municipal'])}}}")
    cc = e.get("contingencias_climaticas")
    if cc:
        lineas.append(f"Denuncia de daños ({escapar(cc.get('delegacion', ''))}): \\textbf{{{escapar(cc.get('telefono', ''))}}}")
    return "{\\small " + "\\\\\n".join(lineas) + "}"


def panel_latex(resultados: dict) -> str:
    """LaTeX de la primera página con los datos del turno; vacío si no hay datos para mostrar."""
    pron = resultados.get("get_weather_forecast")
    riesgo = resultados.get("evaluate_risk")
    caudal = resultados.get("get_river_discharge")
    enso = resultados.get("get_enso_status")
    web = resultados.get("web_search")
    if not (pron or riesgo or caudal):
        return ""
    amenazas = (riesgo or {}).get("amenazas") or []
    titulo = lambda t: f"\\noindent{{\\color{{navy}}\\bfseries {t}}}\\par\\smallskip\n"
    partes = [_encabezado(pron, riesgo, enso, caudal)]
    if amenazas:
        partes.append(_tarjetas(amenazas))
    if pron:
        partes.append("\\noindent\\begin{minipage}[t]{0.58\\textwidth}\n" + titulo("Lluvia diaria")
                      + _grafico_lluvia(pron.get("dias") or []) + "\n\\end{minipage}\\hfill"
                      "\\begin{minipage}[t]{0.38\\textwidth}\n" + titulo("Indicadores")
                      + _indicadores(pron.get("indicadores")) + "\n\\end{minipage}\n\n\\medskip\n")
    if riesgo:
        partes.append(_cronograma(riesgo.get("ventanas") or {}, amenazas))
    partes.append("\\noindent\\begin{minipage}[t]{0.48\\textwidth}\n" + titulo("Caudal del río") + _caudal(caudal)
                  + "\n\\end{minipage}\\hfill\\begin{minipage}[t]{0.46\\textwidth}\n" + titulo("Alertas oficiales")
                  + _alertas(web) + "\\par\\medskip\n" + titulo("Contactos de emergencia") + _contactos(pron)
                  + "\n\\end{minipage}\n")
    return "\n".join(partes) + "\n\\newpage\n"
