# datos/climatologia/

Media histórica de caudal por río, que usa `get_river_discharge` para calcular el cociente caudal previsto / media.

Se genera **una sola vez** y se commitea:

```bash
python scripts/calcular_climatologia.py            # los 4 ríos
python scripts/calcular_climatologia.py tunuyan    # uno solo
```

Por qué no se usa `river_discharge_mean` de la Flood API: es la media del ensamble del pronóstico, no una media histórica.

## Formato de `<rio>.json`

```json
{
  "rio": "tunuyan",
  "fuente": "Open-Meteo Flood API (GloFAS v4), river_discharge diario",
  "punto": {"latitud": -33.78, "longitud": -69.27},
  "periodo": "1991-01-01/2020-12-31",
  "ventana_dias": 15,
  "dias_validos": 10950,
  "media_anual_m3s": 31.2,
  "generado": "2026-11-20",
  "media_por_dia_del_anio": [12.3, 12.4, "... 366 valores, índice 0 = 1 de enero; el 29/2 es el índice 59"]
}
```

`get_river_discharge` toma, para cada día del pronóstico, `media_por_dia_del_anio[dia_del_anio - 1]` (con el calendario de años bisiestos) y promedia esos valores en el período.
