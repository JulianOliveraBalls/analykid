---
description: Secciones obligatorias del plan de contingencia, mínimos de contenido y un ejemplo de cuerpo LaTeX probado. Cargala antes de escribir el informe; create_pdf rechaza el informe si falta algo.
---
# Skill: informe de riesgo

Usá estos títulos de `\section` en este orden (create_pdf verifica cómo empiezan):

1. **Resumen**: finca, período, nivel máximo, etapa del cultivo y las 2-3 medidas más urgentes.
2. **Contexto de temporada**: ENSO (fase, valor, fecha del dato) y lo que dice el corpus de la temporada, con cita.
3. **Etapa del cultivo** (solo vid): la etapa y el período crítico que devolvió evaluate_risk, aclarando que son aproximados.
4. **Pronóstico y días críticos**: tabla diaria y, debajo, una lista con cada día crítico, su motivo y la acción concreta para ese día.
5. **Caudal del río**: máximo y fecha, media 1991-2020, cociente, tendencia y la limitación de los embalses.
6. **Alertas oficiales y contraste de fuentes**: alertas (marcadas ALERTA) con dominio, fecha y URL, o «Sin alertas oficiales encontradas al <fecha>; no implica ausencia de riesgo». Después, qué dicen el pronóstico, las alertas y el corpus, si coinciden y cuál prima.
7. **Semáforo**: las cinco filas con el nivel de evaluate_risk **tal cual** (`Pluvial & \nivel{amarillo} & motivo (umbral; origen) \\`).
8. **Medidas por amenaza**: una `\subsection` por cada amenaza en amarillo o más, empezando por la sanitaria si la vid está en período crítico. En cada una, al menos 3 medidas repartidas en *Antes*, *Durante* y *Después*, cada medida con su cita [Documento — Sección] del corpus. Sin respaldo en el corpus, decilo.
9. **Escalamiento**: los disparadores de evaluate_risk y qué cambia en cada caso (por ejemplo, suspender tareas, evacuar sectores bajos, avisar a Defensa Civil).
10. **Checklist y organización del personal**: quién avisa y quién decide, dónde refugiarse, y una lista de verificación con `\item[\casilla]`.
11. **Contactos de emergencia**: copiados tal cual; sin contacto municipal verificado, solo 911.
12. **Fuentes**: datos (NOAA, Open-Meteo, Flood API, alertas con URL) y cada documento del corpus citado.
13. **Limitaciones**: CAPE indirecto, GloFAS sin embalses, etapa aproximada, umbrales definidos por el equipo (salvo el sanitario, regla 10:10:24), puntos sin verificar y tools con error.

Si el usuario cambia algo en un turno siguiente, el informe nuevo es completo: no remitas al anterior.

## Ejemplo de cuerpo (compila y pasa el control de create_pdf)
```latex
\section{Resumen}
Finca de vid de 10 ha en Tupungato (Valle de Uco), del 20/11 al 26/11. Nivel máximo: \nivel{amarillo}. La vid está en floración, período crítico de peronóspora. Urgente: protector antes de la lluvia del 24/11 y acequias limpias.

\section{Contexto de temporada}
El Niño fuerte (RONI +1.97, ASO 2026). Emergencia hídrica provincial [Temporada 2026-2027 en Mendoza — Emergencia hídrica y climática en Mendoza].

\section{Etapa del cultivo}
Floración (aproximada). Período crítico de peronóspora: 15/10 al 20/12.

\section{Pronóstico y días críticos}
\begin{longtable}{lrrrrr}
\toprule
Fecha & Lluvia (mm) & Prob. (\%) & CAPE (J/kg) & Ráfaga (km/h) & Mín/Máx (°C) \\
\midrule
\endhead
24/11 & 12.0 & 71 & 320 & 32 & 11.1/19.8 \\
26/11 & 1.9 & 37 & 900 & 37 & 12.1/20.0 \\
\bottomrule
\end{longtable}
\begin{itemize}
\item 24/11: lluvia de 12.0 mm, favorable a hongos. Aplicar el protector el 23/11.
\end{itemize}

\section{Caudal del río}
Tunuyán: máximo 21 m³/s, media 21 m³/s, cociente 0.98, estable. GloFAS no modela los embalses.

\section{Alertas oficiales y contraste de fuentes}
Sin alertas oficiales encontradas al 20/11/2026; no implica ausencia de riesgo. El pronóstico diario de Contingencias anticipa lluvias débiles: coincide con Open-Meteo.

\section{Semáforo}
\begin{tabular}{llp{8cm}}
\toprule
Amenaza & Nivel & Motivo (umbral; origen) \\
\midrule
Pluvial & \nivel{amarillo} & Lluvia máx. 12.0 mm el 24/11 (≥ 10 mm; Open-Meteo) \\
Granizo / tormenta & \nivel{verde} & CAPE máx. 900 J/kg el 26/11 (< 1000 J/kg; Open-Meteo) \\
Aluvional & \nivel{verde} & Lluvia 12.0 mm y CAPE 900 J/kg (< 1000 J/kg) \\
Crecida & \nivel{verde} & Cociente 0.98 (< 1.5; GloFAS) \\
Sanitaria & \nivel{amarillo} & 1 día favorable a hongos (≥ 1; regla 10:10:24) \\
\bottomrule
\end{tabular}

\section{Medidas por amenaza}
\subsection{Sanitaria (prioridad: período crítico)}
\begin{itemize}
\item Antes: protector antes de la lluvia, cubriendo el envés [Peronóspora de la vid después de la lluvia — Estrategia preventiva: tratar antes de la lluvia].
\item Después: monitorear manchas de aceite a los 5-10 días [Peronóspora de la vid después de la lluvia — Monitoreo del viñedo después de la lluvia].
\end{itemize}
\subsection{Pluvial}
\begin{itemize}
\item Antes: limpiar acequias y desagües [Finca y viñedo ante aluvión, crecida o inundación — Antes del aluvión o la inundación: preparación de la finca].
\item Después: drenar el agua acumulada [Finca y viñedo ante aluvión, crecida o inundación — Después: drenar el viñedo en los primeros 3 días].
\end{itemize}

\section{Escalamiento}
Pluvial pasa a naranja si la lluvia diaria prevista es ≥ 25 mm o hay alerta naranja: suspender tareas en sectores bajos.

\section{Checklist y organización del personal}
El encargado sigue las alertas y ordena el corte de tareas.
\begin{itemize}
\item[\casilla] Acequias y desagües limpios.
\item[\casilla] Protector aplicado antes del 24/11.
\end{itemize}

\section{Contactos de emergencia}
Emergencias: 911.

\section{Fuentes}
Open-Meteo: \url{https://open-meteo.com}. Corpus: Peronóspora de la vid después de la lluvia; Finca y viñedo ante aluvión, crecida o inundación.

\section{Limitaciones}
CAPE es indirecto; GloFAS no modela embalses; etapa aproximada; umbrales del equipo salvo el sanitario.
```
El ejemplo es corto a propósito: en el informe real cada amenaza activa lleva al menos 3 medidas.
