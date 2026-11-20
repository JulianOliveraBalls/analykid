---
description: Cómo escribir el cuerpo LaTeX del informe para create_pdf (macros de la plantilla, tablas, escapado de caracteres) para que compile al primer intento. Cargala una vez por conversación.
---
# Skill: LaTeX para create_pdf

## Qué escribís y qué agrega la herramienta
- Escribís **solo el cuerpo**: lo que va entre `\begin{document}` y `\end{document}`.
- La plantilla ya pone el título, «AnalyKid», la fecha y, al pie de cada página, el descargo «Este informe no reemplaza las alertas oficiales del SMN ni las indicaciones de Defensa Civil». No los repitas.
- Ya están cargados: fontspec, babel (español), geometry, xcolor, booktabs, longtable, fancyhdr y hyperref. **No uses** `\usepackage`, `\documentclass`, `\input`, `\include`, `\write`, `\catcode`, `\csname`, `\special` ni `^^`: la herramienta rechaza el documento.
- Escribí con caracteres normales (á, é, ñ, °, ³, «», —). No uses comandos para los acentos.

## Macros de la plantilla
- `\nivel{verde}`, `\nivel{amarillo}`, `\nivel{naranja}`, `\nivel{rojo}` y `\nivel{sindatos}`: recuadro de color con el nivel. Usá exactamente esas cinco claves, en minúscula y sin espacios.

## Estructura
- Secciones: `\section{...}` y `\subsection{...}`.
- Párrafos: separalos con una **línea en blanco**; no uses `\\` para separar párrafos.
- Negrita `\textbf{...}`, cursiva `\emph{...}`.
- Listas: `\begin{itemize} \item ... \end{itemize}`; cada `\item` va dentro de una lista.
- Enlaces: `\url{https://...}` (adentro no se escapa nada).

## Tablas
- Tablas cortas (semáforo, caudal): `tabular` con booktabs:
  `\begin{tabular}{lll} \toprule A & B & C \\ \midrule ... \\ \bottomrule \end{tabular}`
- Tablas que pueden ocupar más de una página (pronóstico de 7 a 16 días): `longtable`, con el mismo esquema de reglas.
- Columnas con texto largo: `p{6cm}` en lugar de `l`.
- Cada fila tiene exactamente tantas `&` como columnas menos una y termina en `\\`.
- No pongas `\nivel{...}` dentro de una celda `p{...}` junto con texto largo: dejalo en su propia columna.

## Escapado de caracteres
Fuera de `\url{...}`, estos caracteres se escapan siempre:

| Escribí | Para obtener |
|---|---|
| `\%` | % |
| `\&` | & |
| `\$` | $ |
| `\#` | # |
| `\_` | _ |
| `\{` `\}` | { } |

- Los porcentajes son el error más común: «prob. 60 \%».
- Las claves con guion bajo (`san_rafael`) se escriben `san\_rafael`, o mejor con el nombre normal: San Rafael.
- `≥` y `≤` se pueden escribir tal cual.

## Valores
- Copiá los números **tal como los devuelven las tools** (mismo redondeo y unidad). No los recalcules ni los redondees de nuevo.
- Fechas en formato dd/mm.

## Si la compilación falla
- El error indica la línea del `.tex`; restale la línea donde empieza el cuerpo (viene en el mensaje) para ubicarla en tu texto.
- Causas típicas: un `%` o `&` sin escapar, una fila de tabla con columnas de más o de menos, una llave sin cerrar.
- Corregí solo eso y reintentá. Máximo 3 intentos.
