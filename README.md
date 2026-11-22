<img src="assets/analykid-logo.svg" alt="" width="72">

# AnalyKid

Agente hecho con `create_agent` de LangChain que arma un **plan de contingencia en PDF** ante el riesgo hídrico y climático de fincas y localidades de Mendoza durante El Niño 2026-2027.

Consulta el estado de El Niño (NOAA), el pronóstico (Open-Meteo), el caudal de los ríos (Flood API, GloFAS) y las alertas oficiales (SMN, Gobierno de Mendoza, Irrigación, INA). Calcula en código un semáforo por amenaza (pluvial, granizo/tormenta, aluvional, crecida y sanitaria) y la etapa del cultivo con `evaluate_risk`, busca medidas con cita en una base de conocimiento propia y compila el informe con Tectonic. La interfaz de Streamlit muestra en vivo el recorrido del agente, paso a paso: la cadena de pensamiento del modelo y, por cada tool, la invocación, los parámetros que le pasa y el resultado que recibe. La memoria por conversación permite seguir con «¿y si la finca estuviera en San Rafael?».

## Requisitos

- Python 3.10 o superior y Git
- `GOOGLE_API_KEY` ([AI Studio](https://aistudio.google.com/apikey)): modelo y embeddings del RAG
- `TAVILY_API_KEY` ([Tavily](https://app.tavily.com)): búsqueda de alertas oficiales
- [Tectonic](https://tectonic-typesetting.github.io/book/latest/installation): compilador de LaTeX para el PDF

## Instalación

```bash
git clone https://github.com/JulianOliveraBalls/analykid.git
cd analykid
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # Windows: Copy-Item .env.example .env
```

Completá las claves en el `.env`. Por defecto se usa `gemini-3.5-flash-lite` con `THINKING_LEVEL=medium` (tier gratuito: 15 pedidos por minuto y 500 por día; Gemini 2.5 Flash tiene un límite diario mucho menor). Con `MODEL_PROVIDER=openrouter` se usa OpenRouter como respaldo.

**Tectonic.** Linux y macOS: `brew install tectonic` o `conda install -c conda-forge tectonic`. Windows: descargá `tectonic.exe` desde [releases](https://github.com/tectonic-typesetting/tectonic/releases). Si no queda en el `PATH`, definí `TECTONIC_PATH` en el `.env`. La primera compilación descarga paquetes y tarda: corré los tests una vez antes de la demo.

**Base de conocimiento** (una vez, y cada vez que cambien los documentos de `rag/docs/`):

```bash
python -m rag.ingest
python -m rag.evaluar              # opcional: acierto@4 sobre 12 preguntas
```

## Ejecución

```bash
streamlit run app.py
```

La consulta se arma con el formulario de la barra lateral (localidad, perfil, superficie y días), con los ejemplos de la pantalla inicial o escribiendo en el chat. Cada respuesta muestra arriba el semáforo por amenaza, el mapa y pestañas con pronóstico, caudal, alertas, fuentes y el PDF; después, la respuesta final; y abajo, el recorrido del agente.

**Recorrido del agente.** Cada respuesta del modelo es un paso. En cada paso se ve la cadena de pensamiento (el razonamiento que expone el modelo y lo que anuncia) y, por cada tool que pidió, cuatro cosas: la invocación (qué tool), los parámetros exactos que le pasó el modelo (JSON), el resultado que recibió (el texto completo del `ToolMessage`) y si terminó bien o con error. Las tools de un mismo paso se piden en paralelo. El recorrido del último turno queda desplegado; los anteriores, plegados.

Demo en dos turnos:

1. «Armame el plan de contingencia para una finca de vid de 10 hectáreas en Tupungato para los próximos 7 días».
2. «¿Y si la finca estuviera en San Rafael?»: conserva vid, 10 ha y 7 días; cambia la localidad y el río (Tunuyán → Diamante) y regenera el PDF.

## Tests

```bash
python -m pytest
```

No usan red ni el modelo: datos, `pedir()` ante 429 y timeout, indicadores de cada tool, filtros de alertas, corpus del RAG y plantilla del PDF (la compilación se saltea si falta Tectonic).

## Estructura

```
├── app.py            # UI de Streamlit: formulario, panel (semáforo, mapa, pestañas, PDF) y recorrido paso a paso
├── .streamlit/       # tema de la interfaz
├── assets/           # logo de la app
├── agente.py         # system prompt (flujo y semáforo), create_agent, memoria y streaming
├── model.py          # Gemini u OpenRouter, con reintentos ante 429; embeddings
├── tools/            # common.py (estado, respond, pedir) y una tool por archivo:
│                     # enso, weather, river, web_search, risk (evaluate_risk), knowledge, report
├── datos/            # catálogos: localidades, variables, ríos, dominios oficiales,
│                     # fenologia (calendario de la vid), climatologia/ (medias 1991-2020) y respaldo/ (RONI)
├── rag/              # docs/ (6 documentos), ingest.py, store.py, evaluar.py
├── skills/           # fuentes_datos, informe_riesgo y latex
├── scripts/          # generación de datos: climatología, respaldo ENSO, localidades
└── tests/
```

Se generan al usar la app (no se versionan): `memoria.db`, `conversaciones.txt`, `rag/chroma_db/`, `datos/cache/` y `output/`.

## Datos de referencia

Se generan una vez con los scripts y se commitean:

```bash
python scripts/calcular_climatologia.py      # medias de caudal 1991-2020 por río
python scripts/descargar_respaldo_enso.py    # copia del RONI para funcionar sin red
```

## Notas

- **Razonamiento:** Gemini devuelve resúmenes de su razonamiento con `include_thoughts=True` (en Gemini 3+, además, con `THINKING_LEVEL`) y la UI los muestra en «Cadena de pensamiento», dentro de cada paso del recorrido. Si el modelo no los devuelve en un paso, la UI lo dice en ese paso y todo lo demás funciona igual.
- **Errores:** ninguna tool lanza excepciones. Ante una falla devuelven `ERROR <tool>: <causa>. <qué hacer>` y el agente sigue: la amenaza afectada queda «sin datos», nunca en verde. El 429 y el 503 del modelo los reintenta el cliente con espera exponencial; si persisten, `ModelFallbackMiddleware` (el único middleware) repite la llamada con `MODEL_FALLBACK`. Los de las APIs los reintenta `pedir()` (2, 4 y 8 s).
- **PDF:** Tectonic corre sin shell, con argumentos fijos y en modo `--untrusted`, y el cuerpo se filtra con una lista de comandos prohibidos. Es adecuado para uso local.
- El informe **no reemplaza** las alertas oficiales del SMN ni las indicaciones de Defensa Civil.

## Solución de problemas

| Síntoma | Causa probable |
|---|---|
| Al iniciar: «Falta ... API_KEY» | Clave ausente en el `.env` |
| `ERROR create_pdf: no se encontró Tectonic` | No instalado o fuera del `PATH`: definí `TECTONIC_PATH` |
| `ERROR search_knowledge_base: falta la base vectorial` | No se ejecutó `python -m rag.ingest` |
| «Se alcanzó el límite del proveedor» | 429 del modelo: esperá un minuto y repetí |
| «El modelo está saturado» | 503 de Gemini en ambos modelos: esperá unos minutos o configurá otro `MODEL_FALLBACK` |
| `ERROR web_search: falta TAVILY_API_KEY` | Clave de Tavily ausente: el informe sale sin alertas oficiales |

## Créditos

Los documentos de `rag/docs/` resumen guías de los organismos citados en el frontmatter de cada archivo (INTA, Defensa Civil de Mendoza, DGI, SENAPRED, AWRI, entre otros); cada fragmento conserva su fuente y su URL.
