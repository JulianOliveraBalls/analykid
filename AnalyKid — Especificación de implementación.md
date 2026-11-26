# AnalyKid — Especificación de implementación

Nov 20, 2026 · @ActiveHub

## 1. Objetivo y alcance

AnalyKid es un agente hecho con `create_agent` de LangChain que arma un plan de contingencia en PDF ante el riesgo hídrico y climático de Mendoza durante El Niño 2026-2027.

- **Turno 1 (tarea completa):** «Armame el plan de contingencia para una finca de vid de 10 hectáreas en Tupungato para los próximos 7 días».
- **Turno 2 (memoria):** «¿Y si la finca estuviera en San Rafael?». Conserva vid, 10 ha y 7 días; cambia localidad y río (Tunuyán → Diamante) y regenera el PDF.
- **Resultado:** PDF descargable con contexto de temporada, pronóstico por día, caudal, alertas oficiales, semáforo por amenaza con motivo y umbral, contraste de fuentes, medidas con plazo y cita, contactos de emergencia y fuentes.
- **Amenazas:** pluvial, granizo/tormenta, aluvional, crecida y sanitaria (hongos), cada una en verde, amarillo, naranja o rojo.
- **Alcance validado:** perfil `vid`; Tupungato, San Rafael y Luján de Cuyo; ríos Tunuyán, Diamante y Mendoza; 7 días. El resto del catálogo (20 localidades, perfiles `frutal`, `hortaliza` y `urbano`, 1 a 16 días) queda cargado pero no validado.
- **Fuera de alcance:** coordenadas libres, emitir alertas propias, búsqueda web fuera de dominios oficiales, Zonda, heladas y nieve.

## 2. Requisitos y restricciones de la consigna

Un requisito obligatorio ausente deja su criterio en «No logrado»: esta tabla es el checklist antes del último commit.

| Requisito (consigna) | Cómo se cumple |
| --- | --- |
| Tarea de varios pasos, no resoluble con una llamada ni con un solo tool | 5 pasos y 8 tools encadenadas (sección 3) |
| Resultado tangible, no solo chat | PDF generado con Tectonic |
| Dominio acotado | Riesgo hídrico y climático en Mendoza, temporada 2026-2027 |
| `create_agent`; sin Deep Agents | `agente.py` con `create_agent` |
| Mínimo 3 tools, todas necesarias | 8 tools; cada una aporta una parte del informe |
| Al menos 1 tool propia | Las 4 de datos (ENSO, pronóstico, caudal, alertas) y `evaluate_risk` |
| Al menos 1 tool externa | NOAA, Open-Meteo, Flood API, Tavily; `create_pdf` escribe en disco |
| Nombre, descripción y argumentos bien definidos | Docstring de 3 a 5 líneas; argumentos con `Literal` y rangos validados |
| Errores sin romper el flujo | Ninguna tool lanza excepciones: devuelven `ERROR` legible |
| Memoria con checkpointer, demostrada | `SqliteSaver` por `thread_id`; turno 2 depende del 1 |
| UI web que renderiza markdown | Streamlit + `st.markdown` |
| Cada tool con argumentos y resumen del resultado, en orden, en streaming | `stream_mode="values"` + «Recorrido del agente, paso a paso»: por cada tool, la invocación, los parámetros y el resultado completo |
| Razonamiento diferenciado si el modelo lo expone; si no, documentarlo | `include_thoughts=True` + `thinking_level`; bloques `reasoning` en «Cadena de pensamiento», al comienzo de cada paso |
| Conocimiento propio: RAG (≥ 3 documentos, cita de origen, usado en el flujo principal) o skills | RAG con 6 documentos y cita, más 3 skills (sección 6) |
| Tamaño de lo recuperado acorde al contexto | k = 4, fragmentos ≤ 900 caracteres, ≤ 7 consultas por informe (la de temporada siempre) |
| Middleware mínimo y justificado | Dos: modelo de respaldo ante 503/429 y recordatorio cuando el modelo anuncia sin actuar (sección 8) |
| Modelo con tool calling | `gemini-3.5-flash-lite` (respaldo `gemini-3.1-flash-lite`) |
| Manejo de 429 con reintentos; demo con pocas llamadas | Reintentos en el cliente y en las tools; llamadas en paralelo |
| Repo: código ejecutable, README, `.env.example` sin claves, `requirements.txt`, ingesta reproducible | Sección 9 |
| Presentación: caso, modelo y por qué, diagrama del flujo, justificación de componentes, limitaciones y mejoras | Diapositivas del grupo |
| Demo: tarea completa, flujo de tools, razonamiento, turno con memoria, resultado final | Turnos 1 y 2 con el PDF |
| Defensa individual de cualquier componente | Todos conocen esta especificación completa |

## 3. Flujo del agente

Cinco pasos; dentro de cada paso, las tools se piden en paralelo en una sola respuesta del modelo. Son 5 llamadas al modelo (hasta 7 si `create_pdf` pide correcciones).

1. **Datos:** `get_weather_forecast`, `get_river_discharge` y `web_search` con la misma localidad. Solo en el primer turno, además, `get_enso_status` y `load_skill("fuentes_datos")`.
2. **Evaluación:** `evaluate_risk(perfil)` lee del estado los resultados del paso 1 y calcula semáforo, etapa del cultivo, días críticos, ventanas de fechas, escalamiento y consultas sugeridas para el corpus.
3. **Conocimiento:** `search_knowledge_base` con cada consulta sugerida, más `load_skill("informe_riesgo")` y `load_skill("latex")` si no están en el historial.
4. **Informe:** `create_pdf` controla el contenido contra `evaluate_risk` y compila; si devuelve `ERROR`, el modelo corrige (máximo 3 intentos).
5. **Respuesta final:** nivel máximo, amenazas activas, medidas urgentes y nombre del PDF.

En el turno 2 se repiten los pasos 1 (sin ENSO ni `fuentes_datos`) a 5 para la nueva localidad.

## 4. Tools

Ocho tools en el paquete `tools/`. Las cuatro de datos y `evaluate_risk` son propias; las de conocimiento e informe se adaptan del código de la cátedra.

| Tool | Entrada | Fuente | Devuelve al modelo |
| --- | --- | --- | --- |
| `get_enso_status` | `trimestres` (1-12, def. 4) | NOAA `RONI.ascii.txt` (índice oficial desde 2026) | Fase, valor, categoría (débil a muy fuerte), tendencia, episodio oficial y fecha del dato. ≤ 400 car. |
| `get_weather_forecast` | `localidad` (clave o nombre del catálogo), `dias` (1-16, def. 7) | Open-Meteo `/v1/forecast`, zona `America/Argentina/Mendoza` | Cabecera (departamento, oasis, piedemonte, río, contactos: 911, Defensa Civil municipal verificada y Contingencias Climáticas), tabla por día e indicadores: lluvia acumulada y máxima, prob. máxima, CAPE máximo, ráfaga máxima, mínima más baja, días ≥ 10 mm y días favorables a hongos (≥ 10 mm y mínima ≥ 10 °C). ≤ 1.400 car. |
| `get_river_discharge` | `localidad` (el río sale del catálogo), `dias` (1-30) | Flood API `daily=river_discharge` en el punto de `datos/rios.json` | Caudal máximo y fecha, media 1991-2020 del período, cociente máximo/media y tendencia. ≤ 600 car. |
| `web_search` | `zona` (la tool arma la consulta) | Tavily con `include_domains` desde `datos/dominios_oficiales.json`: smn.gob.ar, mendoza.gov.ar, irrigacion.gov.ar, ina.gob.ar | Hasta 3 resultados (fecha, dominio, título, resumen, URL) y cantidad de descartados. Cada uno marcado ALERTA o «información oficial». Sin resultados locales prueba con la zona provincial. Sin resultados: «Sin alertas oficiales encontradas al \<fecha>; no implica ausencia de riesgo». ≤ 1.500 car. |
| `evaluate_risk` | `perfil`: `Literal["vid","frutal","hortaliza","urbano"]` (los datos los lee del estado) | Resultados del turno de las tres tools de datos, `datos/fenologia.json` | Nivel, motivo, umbral y origen por amenaza; nivel máximo; etapa del cultivo; días críticos; ventanas antes/durante/después con fechas; disparadores de escalamiento; consultas para el corpus. |
| `search_knowledge_base` | `consulta` | Chroma + `gemini-embedding-001`, k = 4 | 4 fragmentos: documento, sección, organismo y ámbito (local o internacional), y el texto. ≤ 3.600 car. |
| `load_skill` | `nombre` | `skills/<nombre>.md` | El contenido de la skill; si no existe, la lista de skills. ≤ 9.000 car. |
| `create_pdf` | `titulo`, `cuerpo` (LaTeX) | Tectonic sobre una plantilla fija | Ruta del PDF, o la lista de problemas de contenido o el error de compilación para corregir. ≤ 1.500 car. |

**Reglas de implementación:**

- **Nunca lanzan excepciones.** Ante una falla devuelven `ERROR <tool>: <causa>. <qué puede hacer el agente>`.
- **Doble canal.** `respond(runtime, texto, artifact=...)`: texto breve al modelo; datos completos (tablas, series, resultados descartados) a la UI, fuera del contexto.
- **Lectura del estado.** `resultados_del_turno(mensajes)` en `tools/common.py` devuelve el último artifact válido de cada tool del turno; lo usan `evaluate_risk` y `create_pdf`, así el modelo no copia datos.
- **HTTP.** Helper `pedir(url, params, cuerpo=...)` en `tools/common.py`: GET o POST, timeout de 20 s, 4 intentos con espera de 2, 4 y 8 s ante 429, 5xx o timeout; devuelve `(datos, error)`.
- **Indicadores calculados en la tool**, nunca por el modelo. Redondeo: 1 decimal para mm y °C, 2 para el índice ENSO; enteros para %, km/h, J/kg y m³/s.
- **`get_enso_status`:** caché en `datos/cache/` y respaldo versionado en `datos/respaldo/` si falla la red.
- **`get_weather_forecast`:** el modelo nunca pasa coordenadas ni elige variables (las variables están en `datos/variables.json`). Localidad inexistente → error con las 3 claves más parecidas (`difflib.get_close_matches`).
- **`get_river_discharge`:** cada punto de `rios.json` se verifica a mano antes de cargarlo (la API toma el río más grande en 5 km). La media sale de `datos/climatologia/<rio>.json`, generada una vez por `scripts/calcular_climatologia.py` (1991-2020, ±15 días); `river_discharge_mean` de la API es la media del ensamble, no histórica.
- **`web_search`:** llama a la API REST de Tavily con `topic="news"` y `time_range="week"`; descarta en código los resultados de otros dominios, de más de 48 horas o sin fecha. Sin clave o sin red → `ERROR` y el agente sigue sin alertas.
- **`create_pdf`:** `--untrusted`, sin shell, lista de comandos prohibidos, timeout de 180 s. Antes de compilar, `validar()` exige las 13 secciones (más «Etapa» en vid), los niveles del semáforo iguales a `evaluate_risk`, «Antes (fechas)», «Durante (fechas)» y «Después (fechas)» por amenaza activa al menos 3 citas por amenaza activa, y cada bloque como lista con 2, 1 y 2 medidas como mínimo, de al menos 80 caracteres sin la cita (qué hacer, cómo, qué mirar y dónde). Las amenazas en verde no pueden llevar bloques con fechas y deben aparecer en «Vigilancia». Plantilla con `xcolor`, `longtable`, macros `\nivel{verde|amarillo|naranja|rojo|sindatos|noaplica}` y `\casilla`, y pie con el descargo «Este informe no reemplaza las alertas oficiales del SMN ni las indicaciones de Defensa Civil».

## 5. Semáforo: umbrales y reglas

Los umbrales están en `tools/risk.py` y los aplica `evaluate_risk` en código; el modelo copia los niveles y `create_pdf` verifica que coincidan.

| Amenaza | Indicador | Amarillo | Naranja | Rojo |
| --- | --- | --- | --- | --- |
| Pluvial | Lluvia máxima diaria | ≥ 10 mm | ≥ 25 mm | ≥ 50 mm |
| Granizo / tormenta | CAPE máximo (J/kg) | ≥ 1.000 | ≥ 2.000 | ≥ 3.000 |
| Aluvional (solo piedemonte) | Lluvia máx. y CAPE máx. | ≥ 10 mm y ≥ 1.000 | ≥ 20 mm y ≥ 1.500 | ≥ 35 mm y ≥ 2.000 |
| Crecida | Cociente caudal máx. / media | ≥ 1,5 | ≥ 2,0 | ≥ 3,0 |
| Sanitaria (no aplica a `urbano`) | Días favorables a hongos | 1 | 2 | ≥ 3 |

El umbral sanitario sigue la regla 10:10:24 de la peronóspora; los demás son supuestos del equipo y se declaran como tales.

1. Sin umbral alcanzado → verde. Tool con `ERROR` → «sin datos», nunca verde.
2. Granizo: si la probabilidad de precipitación de ese día es ≥ 60 %, sube un nivel (máximo rojo).
3. Aluvional: fuera del piedemonte, máximo amarillo.
4. El ENSO no cambia el nivel diario: es contexto de temporada.
5. Cada nivel se informa con motivo, umbral aplicado y origen: «Naranja: CAPE máx. 2.300 J/kg el 18/11 (umbral ≥ 2.000)».
6. **Jerarquía de fuentes:** una alerta oficial vigente fija el nivel mínimo. Si los datos dan más, se usa el más alto con la etiqueta «señal del pronóstico, sin alerta oficial vigente». Nunca se llama «alerta» a algo no oficial; sin alertas encontradas nunca es «no hay riesgo».
7. Crecida en amarillo o más con lluvia intensa prevista → destacar la combinación lluvia + canales con agua (los ríos están regulados por embalses).
8. Etapa de la vid (`datos/fenologia.json`): si la fecha cae en el período crítico de peronóspora del oasis, las medidas sanitarias van primero; el nivel no cambia.
9. **Ventanas por amenaza activa:** «antes» va de hoy (primer día del pronóstico) al día previo al evento; «durante», los días del evento; «después», 1 a 3 días posteriores (5 a 10 en la sanitaria, cuando aparecen las manchas).
10. **Amenazas en verde:** no llevan medidas con fechas; van en la subsección «Vigilancia» con lo que las activaría. Si ninguna está activa, el informe dice que no hay medidas obligatorias.

## 6. Conocimiento propio: RAG y skills

Se usan las dos opciones: el RAG aporta qué recomendar, con cita; las skills, cómo interpretar los datos y armar el informe.

### Corpus (`rag/docs/`, 6 documentos ya redactados)

| Archivo | Se consulta cuando |
| --- | --- |
| `aluviones_piedemonte.md` | Aluvional ≥ amarillo |
| `finca_aluvion_inundacion.md` | Aluvional, crecida o pluvial ≥ amarillo |
| `tormenta_electrica_trabajo_campo.md` | Granizo / tormenta ≥ amarillo |
| `vid_granizo.md` | Granizo / tormenta ≥ amarillo (vid): una consulta para la revisión de malla, postes y anclajes, y otra para el daño por planta |
| `vid_peronospora_lluvia.md` | Sanitaria ≥ amarillo |
| `temporada_2026_2027_mendoza.md` | Siempre (contexto) y crecida ≥ amarillo |

Formato: frontmatter YAML con `titulo`, `amenaza`, `perfiles` y una lista `fuentes` (`id`, `organismo`, `documento`, `anio`, `ambito`, `url`); secciones `##` de 300 a 800 caracteres, cada una cerrada con `Fuente: <id>`.

### Ingesta (`python -m rag.ingest`)

1. Lee los `.md`, separa el frontmatter (`pyyaml`) y guarda `source`, `titulo`, `amenaza` y `perfiles`.
2. Divide por `##` (`MarkdownHeaderTextSplitter` → metadata `seccion`); `RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=120)` solo para secciones largas.
3. En cada fragmento lee `Fuente: <id>`, la cruza con `fuentes` y guarda `fuente_id`, `organismo`, `ambito`, `anio` y `url`; quita esa línea del texto.
4. Embeddings con `gemini-embedding-001` en lotes con pausa entre lotes.
5. Reinicia la colección y la persiste en `rag/chroma_db/` (no versionada).

### Evaluación (`python -m rag.evaluar`)

`rag/preguntas_eval.json` con 12 preguntas, 2 por documento, cada una con su documento esperado. Métrica: acierto@4 y posición media; meta ≥ 10/12. En la presentación va el valor medido.

### Skills (`skills/`, cargadas con `load_skill`)

- **`fuentes_datos`** (una vez por conversación): cómo se consulta cada fuente, qué devuelve y cómo interpretarla. CAPE es un indicador indirecto de granizo; GloFAS es simulado, a 5 km y no modela embalses; las alertas se filtran por dominio y 48 h.
- **`informe_riesgo`**: las 13 secciones del PDF en orden (resumen, contexto, etapa del cultivo, pronóstico y días críticos, caudal, alertas y contraste, semáforo, medidas por amenaza con antes/durante/después fechados, escalamiento, checklist, contactos, fuentes, limitaciones) y un ejemplo de cuerpo LaTeX que pasa `validar()`.
- **`latex`** (una vez por conversación): macros de la plantilla, escapado de caracteres y regla de copiar los valores de las tools tal cual.

Etapa de la vid (Malbec), cargada en `datos/fenologia.json` con el período crítico por oasis:

| Oasis | Brotación | Floración | Cuaje |
| --- | --- | --- | --- |
| Norte (Luján de Cuyo) | fin sep - inicio oct | fin oct | mediados nov |
| Este | mediados - fin sep | inicio nov | mediados nov |
| Valle de Uco (Tupungato) | fin sep - inicio oct | mediados nov | fin nov (estimado) |
| Sur (San Rafael) | fin sep - inicio oct | fin oct - inicio nov | sin registro |

Diciembre a febrero: crecimiento de bayas y envero; marzo: maduración. Fuentes: Informe Fenológico Campaña 2025 (Dirección de Agricultura de Mendoza) y Rodríguez et al. (2000, UNCuyo). El informe aclara que la etapa es aproximada.

## 7. Memoria, UI y streaming

**Memoria:** `SqliteSaver` sobre `memoria.db`, una conversación por `thread_id`.

- Estado `AnalyKidState(AgentState)` con `sources: Annotated[list[dict], _merge_sources]`; se eliminan `todos`, `write_todos` y `read_todos` del código de referencia.
- Pronóstico y caudal no se guardan en el estado: el modelo los lee de los `ToolMessage` del historial.
- En el turno 2 deben verse `localidad="san_rafael"` en el pronóstico, el caudal (que resuelve el Diamante) y las alertas; no se vuelven a llamar `get_enso_status`, `fuentes_datos` ni `latex`. El PDF sigue diciendo «vid, 10 ha».

**UI (Streamlit, `app.py`, tema en `.streamlit/config.toml`):**

- Barra lateral: formulario (localidad, perfil, superficie, días), conversaciones y modelo activo. Pantalla inicial con ejemplos.
- Panel de resultado: tarjetas del semáforo por amenaza, cronograma antes/durante/después, «Qué haría subir el nivel», mapa de la localidad y el punto del río, ENSO, contactos y descarga del PDF.
- Pestañas: Pronóstico (tabla y gráfico), Caudal (serie contra la media 1991-2020), Alertas, Fuentes e Informe (PDF embebido con `st.pdf`).
- «Recorrido del agente, paso a paso» en vivo con `stream_mode="values"`: cada respuesta del modelo es un paso con su cadena de pensamiento y, por cada tool, la invocación, los parámetros exactos (JSON) y el resultado completo que recibe el modelo; el paso queda en error si algún resultado empieza con `ERROR`.
- Identidad: logo en `assets/`, paleta azul marino en `.streamlit/config.toml` y sin emojis; los únicos colores fuera de la paleta son los del semáforo.
- Respuesta final con `st.markdown`. Errores 503 y 429 con un mensaje claro, sin romper la app.
- Conversaciones guardadas sin algún campo nuevo se completan desde el catálogo.

## 8. Modelo, errores y 429

**Modelo:** `gemini-3.5-flash-lite` (Google AI Studio, tier gratuito: 15 RPM, 500 RPD), `include_thoughts=True` y `thinking_level` desde `THINKING_LEVEL` (sin él no devuelve razonamiento). Ignora la temperatura. Respaldo automático: `MODEL_FALLBACK=gemini-3.1-flash-lite`. OpenRouter sigue soportado en `model.py`.

**System prompt** (`agente.py`), con la fecha del día y `listar_skills()`:

- Si falta localidad o perfil, preguntar una sola vez.
- Antes de cada grupo de tools, explicar en 1-2 líneas qué va a consultar y por qué.
- Seguir los 5 pasos de la sección 3, con las tools de cada paso en paralelo.
- No evaluar niveles: copiarlos de `evaluate_risk`.
- Citar cada medida como `[Documento — Sección]`; si el corpus no la respalda, decirlo; si dos fuentes difieren, prima la local.
- Copiar los contactos de emergencia tal cual (911, Defensa Civil municipal verificada, Contingencias Climáticas).
- En turnos siguientes conservar lo que no cambió; nunca reutilizar pronóstico, caudal ni alertas de otra localidad.
- Nunca inventar datos ni documentos; no recomendar productos comerciales ni dosis.
- Máximo 3 intentos de `create_pdf`.

**Middleware (`agente.py` y `middleware.py`):**

- `ModelFallbackMiddleware`: si el modelo principal falla tras sus reintentos (503 o 429), repite la llamada con `MODEL_FALLBACK`. Justificación: los 503 de Gemini cortaban la demo.
- `continuar_si_solo_anuncia` (`after_model`): si el modelo termina un mensaje anunciando consultas sin hacerlas, sin PDF y sin preguntar nada, agrega un recordatorio interno y vuelve al modelo (máximo 2 por turno). Justificación: pasaba 2 de cada 6 turnos con Flash Lite; reescribir el prompt no lo resolvía.

**Manejo de 429 y errores:**

- Modelo: `max_retries=3` y `timeout=120` en el cliente; después, el modelo de respaldo.
- Tools HTTP: helper `pedir()`. Tavily y embeddings: `try/except` que devuelve `ERROR` legible.
- UI: si el turno falla, muestra el error sin romper la app; con 429, «límite del proveedor, esperá un minuto».

**Presupuesto:** 5 llamadas al modelo por turno (hasta 7 con correcciones del PDF).

**Verificar antes de la demo:** límites actuales del tier de Gemini, de `gemini-embedding-001` y de Tavily; que lleguen los bloques de razonamiento; que el modelo haga las llamadas en paralelo.

## 9. Repositorio, configuración y entrega

```text
analykid/
├── app.py                 # UI Streamlit
├── .streamlit/            # tema de la interfaz
├── agente.py              # system prompt, create_agent, memoria, streaming
├── model.py               # fábrica de modelos, razonamiento, reintentos, respaldo
├── middleware.py          # recordatorio cuando el modelo anuncia sin actuar
├── tools/                 # __init__.py, common.py, enso.py, weather.py, river.py,
│                          # web_search.py, risk.py, knowledge.py, report.py
├── datos/                 # localidades.json, variables.json, rios.json, fenologia.json,
│                          # dominios_oficiales.json, climatologia/, respaldo/
├── rag/                   # docs/, ingest.py, store.py, evaluar.py, preguntas_eval.json
├── skills/                # fuentes_datos.md, informe_riesgo.md, latex.md
├── scripts/               # calcular_climatologia.py, descargar_respaldo_enso.py,
│                          # completar_localidades.py
├── tests/
├── .env.example  .gitignore  .gitattributes  requirements.txt  README.md
```

- **`datos/localidades.json`:** cada localidad con `departamento`, `oasis` (`norte`, `este`, `valle_de_uco`, `sur`, `alta_montana`), `rio`, `piedemonte` y `emergencias` (`general`, `defensa_civil_municipal`, `fuente`, `verificado`, `contingencias_climaticas`). Defensa Civil municipal solo si está publicada en el sitio oficial del municipio (9 localidades al 20/11/2026); el resto, solo 911. Contingencias Climáticas: la delegación del oasis. Se regenera con `scripts/completar_localidades.py --campo emergencias --escribir`.
- **`.env.example` sin claves:** `MODEL_PROVIDER`, `MODEL_NAME`, `THINKING_LEVEL`, `MODEL_FALLBACK`, `GOOGLE_API_KEY` (modelo y embeddings), `TAVILY_API_KEY`, `OPENROUTER_API_KEY` (opcional), `TECTONIC_PATH` (opcional).
- **`requirements.txt` completo:** incluye `requests` (Tavily por REST, sin `langchain-tavily`), `streamlit-pdf`, `pyyaml` y `pytest`; versiones fijadas con `==` desde un `pip freeze` del entorno que funcionó.
- **`.gitignore`:** cambiar `docs/` por `/docs/` (si no, `rag/docs/` no se sube); nunca commitear `.env`, `memoria.db`, `rag/chroma_db/` ni `output/`. `.gitattributes` con `* text=auto eol=lf`.
- **README:** instalación, configuración del `.env`, instalación de Tectonic (compilar una vez para descargar paquetes), `python -m rag.ingest`, ejecución con `streamlit run app.py` y solución de problemas. Probarlo desde cero en otra PC.
- **Tests (`pytest`, sin red):** parseo y clasificación del ENSO, resolución de localidades e indicadores, cociente de caudal, filtros de dominio y fecha de las alertas, `pedir()` ante 429 y timeout, validez del corpus (frontmatter, ids de `Fuente:`, secciones ≤ 900 caracteres), semáforo, ventanas y escalamiento de `evaluate_risk`, `validar()` de `create_pdf`, middleware, lock del RAG, contactos con fuente y compilación de la plantilla (75 tests).
- **Se evalúa el último commit anterior a la exposición.**
