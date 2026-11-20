---
description: Qué devuelve cada tool de datos (ENSO, pronóstico, caudal, alertas) y evaluate_risk, de qué fuente sale, cómo interpretarla y qué limitaciones declarar en el informe. Cargala una vez por conversación.
---
# Skill: fuentes de datos de AnalyKid

Copiá los valores tal como los devuelven las tools: ya vienen calculados y redondeados. No recalcules indicadores ni inventes los que falten.

## get_enso_status (NOAA, índice RONI)
- Qué es: anomalía de temperatura del Pacífico ecuatorial relativa al resto del trópico, en trimestres móviles. Desde 2026 el RONI es el índice oficial de NOAA.
- Lectura: ≥ +0,5 El Niño; ≤ −0,5 La Niña; en el medio, neutral. Intensidad: débil < 1,0; moderado < 1,5; fuerte < 2,0; muy fuerte ≥ 2,0. Un episodio se declara con 5 trimestres consecutivos sobre el umbral.
- Uso: es **contexto de temporada** y **no cambia el nivel de ningún día**. Qué implica para Mendoza esta temporada (emergencia declarada, ríos por encima de la media) sale del corpus: buscalo en search_knowledge_base y citalo.
- Si el texto dice «caché local» o «respaldo versionado», aclará en el informe la fecha del dato.

## get_weather_forecast (Open-Meteo)
- Modelo numérico de pronóstico en la coordenada de la cabecera del departamento, zona horaria de Mendoza. Las variables son siempre las mismas: no las elegís vos.
- Lluvia diaria (mm) y probabilidad máxima (%): base de las amenazas pluvial, aluvional y sanitaria.
- **CAPE máximo (J/kg)**: energía disponible para la convección. Es un indicador **indirecto** de tormenta y granizo: un CAPE alto dice que la atmósfera puede formar tormentas fuertes, no que vaya a granizar en la finca. Decilo así en el informe.
- Ráfaga máxima (km/h) y mínima más baja (°C): se informan en la tabla; no tienen semáforo propio (Zonda y heladas están fuera de alcance).
- Días favorables a hongos: días con ≥ 10 mm y mínima ≥ 10 °C (regla 10:10:24 de la peronóspora).
- La cabecera trae oasis, piedemonte, río y contactos de emergencia.
- La confianza baja con el plazo: a partir del día 4 o 5, tratá los valores como tendencia.

## get_river_discharge (Open-Meteo Flood API, GloFAS)
- Recibe la misma localidad que el pronóstico; el río sale del catálogo y aparece en el texto como `rio=...`.
- Caudal **simulado** por GloFAS en una celda de unos 5 km, aguas arriba de los embalses: representa el caudal natural que llega a Potrerillos, El Carrizal o Agua del Toro.
- **No modela los embalses ni las erogaciones**: aguas abajo, el caudal real depende de la operación de las presas. Declaralo en las limitaciones.
- El indicador es el cociente caudal máximo / media 1991-2020 de las mismas fechas. «Punto sin verificar» significa que la celda todavía no se revisó a mano: mencionalo como limitación.

## web_search (Tavily sobre dominios oficiales)
- Busca solo en smn.gob.ar, mendoza.gov.ar, irrigacion.gov.ar e ina.gob.ar, y descarta lo que no tenga fecha o tenga más de 48 horas.
- Cada resultado viene marcado **ALERTA** (menciona una alerta o aviso meteorológico) o **Información oficial** (pronósticos, comunicados). Solo lo marcado ALERTA puede llamarse «alerta» y fijar el nivel mínimo; la información oficial se usa como contexto en el contraste de fuentes. Citá siempre dominio, fecha y URL.
- Si la zona no dio resultados, la tool busca a nivel provincial y lo aclara: decí en el informe que el aviso es provincial, no de la localidad.
- «Sin alertas oficiales encontradas» **no** significa «sin riesgo»: escribilo tal cual.

## search_knowledge_base (corpus propio)
- Guías de organismos locales e internacionales. Cada fragmento trae documento, sección, organismo y ámbito.
- Citá cada medida como [Documento — Sección]. Si dos fuentes difieren, prima la de ámbito local.
- Si el corpus no respalda una medida, no la inventes: decí que no hay fuente.

## evaluate_risk (cálculo propio)
- Aplica la tabla de umbrales a los indicadores del turno y la regla de alertas oficiales. Sus niveles son los del informe: no los recalcules.
- La etapa de la vid sale de un calendario fenológico aproximado por oasis; el informe debe decir que es aproximada.
- Los umbrales son supuestos del equipo, salvo el sanitario (regla 10:10:24): declaralo en las limitaciones.

## Si una tool devuelve ERROR
- La amenaza que depende de esa tool va como **«sin datos»**, nunca verde.
- Seguí con el resto del informe y explicá en las limitaciones qué faltó y por qué.
