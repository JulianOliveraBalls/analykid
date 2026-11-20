---
description: Estructura del PDF del plan de contingencia, etapa de la vid por oasis y un ejemplo de cuerpo LaTeX probado. Cargala antes de escribir el informe.
---
# Skill: informe de riesgo

## Secciones del informe (en este orden)
1. **Resumen**: finca (perfil, hectáreas, localidad), período, nivel más alto y la medida más urgente, en 3-4 líneas.
2. **Contexto de temporada**: ENSO (fase, valor, fecha del dato) y lo que dice el corpus de la temporada, con cita.
3. **Pronóstico por día**: tabla con fecha, lluvia, probabilidad, CAPE, ráfaga y mínima/máxima.
4. **Caudal del río**: máximo y fecha, media 1991-2020, cociente y tendencia.
5. **Alertas oficiales**: cada una con dominio, fecha y URL, o la frase exacta «Sin alertas oficiales encontradas al <fecha>; no implica ausencia de riesgo».
6. **Semáforo**: una fila por amenaza (pluvial, granizo/tormenta, aluvional, crecida, sanitaria) con nivel, motivo, umbral aplicado y origen del dato.
7. **Contraste de fuentes**: qué dice el pronóstico frente a las alertas oficiales y frente al corpus; si difieren, cuál prima y por qué.
8. **Medidas**: agrupadas por plazo (ahora / próximas 48 h / durante el período / después del evento), cada una con su cita [Documento — Sección]. Solo para amenazas en amarillo o más. Las sanitarias primero si la vid está en período crítico.
9. **Contactos de emergencia**: copiados tal cual de get_weather_forecast; sin contacto municipal verificado, solo 911.
10. **Fuentes**: datos (NOAA, Open-Meteo, Flood API, alertas con URL) y documentos del corpus.
11. **Limitaciones**: CAPE es indirecto, GloFAS no modela embalses, la etapa de la vid es aproximada, tools con error, puntos sin verificar.

## Etapa de la vid (Malbec) por oasis
| Oasis | Brotación | Floración | Cuaje |
|---|---|---|---|
| Norte (Luján de Cuyo) | fin sep - inicio oct | fin oct | mediados nov |
| Este | mediados - fin sep | inicio nov | mediados nov |
| Valle de Uco (Tupungato) | fin sep - inicio oct | mediados nov | fin nov (estimado) |
| Sur (San Rafael) | fin sep - inicio oct | fin oct - inicio nov | sin registro |

Diciembre a febrero: crecimiento de bayas y envero; marzo: maduración. Fuentes: Informe Fenológico Campaña 2025 (Dirección de Agricultura de Mendoza) y Rodríguez et al. (2000, UNCuyo). Aclarar en el informe que la etapa es aproximada.

**Período crítico para peronóspora**: desde brotes de 15-20 cm hasta baya tamaño arveja (aprox. brotación + 3 semanas hasta 3-4 semanas después del cuaje). Si la fecha cae ahí, las medidas sanitarias van primero; el nivel del semáforo no cambia.

## Ejemplo de cuerpo (compila con create_pdf)
```latex
\section{Resumen}
Finca de vid de 10 ha en Tupungato (Valle de Uco), del 20/11 al 26/11. Nivel más alto: \nivel{amarillo} granizo/tormenta. Medida más urgente: revisar la malla antigranizo antes del 26/11 [Granizo en la vid — Antes del granizo: uso de la malla antigranizo].

\section{Pronóstico por día}
\begin{longtable}{lrrrrr}
\toprule
Fecha & Lluvia (mm) & Prob. (\%) & CAPE (J/kg) & Ráfaga (km/h) & Mín/Máx (°C) \\
\midrule
\endhead
20/11 & 0.9 & 54 & 200 & 27 & 9.8/20.8 \\
26/11 & 1.9 & 36 & 1210 & 37 & 12.1/20.0 \\
\bottomrule
\end{longtable}

\section{Semáforo}
\begin{tabular}{llp{8cm}}
\toprule
Amenaza & Nivel & Motivo (umbral; origen) \\
\midrule
Pluvial & \nivel{amarillo} & Lluvia máx. 12.0 mm el 24/11 (umbral ≥ 10 mm; Open-Meteo) \\
Granizo / tormenta & \nivel{amarillo} & CAPE máx. 1210 J/kg el 26/11 (umbral ≥ 1.000; Open-Meteo) \\
Crecida & \nivel{sindatos} & La Flood API no respondió \\
\bottomrule
\end{tabular}

\section{Medidas}
\subsection{Próximas 48 horas}
\begin{itemize}
\item Planificar las tareas a campo según el pronóstico de tormentas [Tormentas eléctricas y trabajo en la finca — Antes de la jornada: planificar el trabajo según el pronóstico].
\end{itemize}

\section{Contactos de emergencia}
Emergencias: 911.

\section{Fuentes}
\begin{itemize}
\item Open-Meteo, pronóstico diario: \url{https://open-meteo.com/en/docs}
\end{itemize}
```
