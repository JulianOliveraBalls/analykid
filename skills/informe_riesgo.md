---
description: Secciones obligatorias del plan de contingencia, mínimos de contenido y un ejemplo de cuerpo LaTeX probado. Cargala antes de escribir el informe; create_pdf rechaza el informe si falta algo.
---
# Skill: informe de riesgo

Usá estos títulos de `\section` en este orden (create_pdf verifica cómo empiezan):

1. **Resumen**: finca, período, nivel máximo, etapa y las 2-3 medidas más urgentes.
2. **Contexto de temporada**: ENSO (fase, valor, fecha del dato) y lo que dice el corpus de la temporada, con cita.
3. **Etapa del cultivo** (solo vid): la etapa y el período crítico que devolvió evaluate_risk, aclarando que son aproximados.
4. **Pronóstico y días críticos**: tabla diaria y, debajo, una lista con cada día crítico, su motivo y la acción concreta para ese día.
5. **Caudal del río**: máximo y fecha, media 1991-2020, cociente, tendencia y la limitación de los embalses.
6. **Alertas oficiales y contraste de fuentes**: alertas (marcadas ALERTA) con dominio, fecha y URL, o «Sin alertas oficiales encontradas al <fecha>; no implica ausencia de riesgo». Después, qué dicen el pronóstico, las alertas y el corpus, si coinciden y cuál prima.
7. **Semáforo**: las cinco filas con el nivel de evaluate_risk **tal cual** (`Pluvial & \nivel{amarillo} & motivo (umbral; origen) \\`).
8. **Medidas por amenaza**: una `\subsection` por amenaza en amarillo o más (la sanitaria primero si la vid está en período crítico). Adentro, tres bloques con las fechas que dio evaluate_risk, escritas tal cual: `\textbf{Antes (20/11 al 23/11):}`, `\textbf{Durante (24/11):}` y `\textbf{Después (25/11 al 27/11):}`, cada uno seguido de su lista `itemize`: al menos 2 medidas en Antes y en Después, y 1 en Durante.
   - Cada medida dice **qué hacer, cómo, qué mirar y dónde** (o quién), con el detalle del fragmento que citás: cantidades, plazos, partes de la planta, lugares de la finca. «Revisar la malla» o «evaluar daños» no alcanzan: decí qué revisar y en qué orden.
   - Si la medida nombra una regla (30/30, 10:10:24), explicala ahí mismo.
   - Cada medida lleva su cita [Documento — Sección]. Si te falta detalle, hacé una búsqueda más específica en search_knowledge_base antes de escribir.
   - Las medidas salen del corpus para esta finca: no copies las del ejemplo.
9. **Escalamiento**: los disparadores de evaluate_risk y qué cambia en cada caso (por ejemplo, suspender tareas, evacuar sectores bajos, avisar a Defensa Civil).
10. **Checklist y organización del personal**: quién avisa y decide, dónde refugiarse, y una lista con `\item[\casilla]`.
11. **Contactos de emergencia**: copiados tal cual de get_weather_forecast: 911, Defensa Civil municipal (si no está verificada, decilo) y Contingencias Climáticas para denunciar daños de granizo o lluvia en la finca.
12. **Fuentes**: datos (NOAA, Open-Meteo, Flood API, alertas con URL) y cada documento citado.
13. **Limitaciones**: CAPE indirecto, GloFAS sin embalses, etapa aproximada, umbrales del equipo (salvo el sanitario), puntos sin verificar y tools con error.

Si el usuario cambia algo en otro turno, el informe nuevo es completo: no remitas al anterior.


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
Sin alertas oficiales encontradas al 20/11/2026; no implica ausencia de riesgo. Contingencias coincide con Open-Meteo.

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
\textbf{Antes (20/11 al 23/11):}
\begin{itemize}
\item Aplicar el protector el 23/11, lo más cerca posible de la lluvia, cubriendo el envés de las hojas y la parte de atrás de los racimos: la barrera impide que entren las esporas [Peronóspora de la vid después de la lluvia — Estrategia preventiva: tratar antes de la lluvia].
\item En floración, acortar el intervalo entre aplicaciones a 5 a 7 días: dejar prevista la siguiente para el 28/11 al 30/11 [Peronóspora de la vid después de la lluvia — Estrategia preventiva: tratar antes de la lluvia].
\end{itemize}
\textbf{Durante (24/11):}
\begin{itemize}
\item Anotar la lluvia en el pluviómetro y la mínima en el termómetro de máximas y mínimas: con ≥ 10 mm y ≥ 10 °C en 24 h (regla 10:10:24) hay riesgo de infección [Peronóspora de la vid después de la lluvia — Monitoreo del viñedo después de la lluvia].
\end{itemize}
\textbf{Después (29/11 al 04/12):}
\begin{itemize}
\item Recorrer unas 200 plantas representativas entre media mañana y media tarde, mirando las dos caras de las hojas [Peronóspora de la vid después de la lluvia — Monitoreo del viñedo después de la lluvia].
\item Buscar manchas de aceite amarillas de 1 cm en la cara superior de las hojas nuevas, con polvillo blanco en el envés, y zonas pardas en los racimos [Peronóspora de la vid después de la lluvia — Síntomas para reconocer la peronóspora].
\end{itemize}
\subsection{Pluvial}
\textbf{Antes (20/11 al 23/11):}
\begin{itemize}
\item Limpiar acequias, desagües y cauces de la finca y sacar basura y ramas: si están tapados, el agua escurre por donde no debe y anega las zonas bajas [Finca y viñedo ante aluvión, crecida o inundación — Antes del aluvión o la inundación: preparación de la finca].
\item Sacar personas, vehículos y maquinaria de badenes, puentes y desembocaduras de cauces, e incluir a los animales en el plan [Finca y viñedo ante aluvión, crecida o inundación — Antes del aluvión o la inundación: preparación de la finca].
\end{itemize}
\textbf{Durante (24/11):}
\begin{itemize}
\item Quedarse en la casa o un edificio cerrado y no circular a pie ni en vehículo: con agua no se ven caminos ni acequias [Aluviones en zonas de piedemonte y cordillera — Durante un aluvión: si se está en un lugar seguro].
\end{itemize}
\textbf{Después (25/11 al 27/11):}
\begin{itemize}
\item Drenar o bombear el agua dentro de los 3 días: zanja poco profunda por el centro de la calle y pozo de bombeo donde el agua quedó encerrada [Finca y viñedo ante aluvión, crecida o inundación — Después: drenar el viñedo en los primeros 3 días].
\item Limpiar canales y pozos con barro antes de regar; si las raíces se dañaron, regar con cuidado para evitar el estrés hídrico [Finca y viñedo ante aluvión, crecida o inundación — Después: canales, acequias y riego].
\end{itemize}

\section{Escalamiento}
Pluvial pasa a naranja si la lluvia diaria prevista es ≥ 25 mm o hay alerta naranja: suspender tareas en sectores bajos.

\section{Checklist y organización del personal}
El encargado sigue las alertas y corta las tareas.
\begin{itemize}
\item[\casilla] Acequias y desagües limpios.
\item[\casilla] Protector aplicado antes del 24/11.
\end{itemize}

\section{Contactos de emergencia}
Emergencias: 911. Defensa Civil de Tupungato: 2622 574912 (guardia 24 h). Denuncia de daños: Contingencias Climáticas, delegación Valle de Uco (Tunuyán), 02622 423036.

\section{Fuentes}
Open-Meteo: \url{https://open-meteo.com}. Corpus: Peronóspora de la vid después de la lluvia; Finca y viñedo ante aluvión, crecida o inundación.

\section{Limitaciones}
CAPE es indirecto; GloFAS no modela embalses; etapa aproximada; umbrales del equipo salvo el sanitario.
```
