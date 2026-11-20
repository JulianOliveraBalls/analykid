# datos/respaldo/

Copias versionadas de los índices ENSO de NOAA, para que `get_enso_status` funcione sin red (por ejemplo, durante la demo).

Orden de lectura de la tool: descarga en línea → `datos/cache/` (no versionada) → este respaldo. El texto al modelo siempre aclara la fecha del dato usado.

Se actualizan con:

```bash
python scripts/descargar_respaldo_enso.py
```

| Archivo | Origen |
| --- | --- |
| `oni.ascii.txt` | https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt |
| `RONI.ascii.txt` | https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt (índice oficial desde la Declaración Pública 26-05 del NWS) |
| `descarga.json` | Fecha y hora de la última descarga de cada archivo |

Actualizarlo justo antes del congelamiento del repo, para que el respaldo traiga el último trimestre publicado.
