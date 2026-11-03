# Inspección de datos originales (Zenodo)

Generado por `scripts/inspect_raw.py`. Solo describe los datos; no los corrige.

## curtailment_daily

293,678 filas · 5 columnas

| columna | tipo | % nulos | distintos | mínimo | máximo |
|---|---|---:|---:|---|---|
| fecha | date32[day] | 0.00 |  | 2022-01-01 | 2026-05-31 |
| central_codigo | string | 0.00 | 300 |  |  |
| tecnologia | string | 0.00 | 4 |  |  |
| mwh | double | 0.00 |  | 0.00 | 4,994.61 |
| archivo_origen | string | 0.00 | 7 |  |  |

## curtailment_hourly

6,906,761 filas · 6 columnas

| columna | tipo | % nulos | distintos | mínimo | máximo |
|---|---|---:|---:|---|---|
| fecha | date32[day] | 0.00 |  | 2022-01-01 | 2026-05-31 |
| hora | int16 | 0.00 | 24 | 1 | 24 |
| central_codigo | string | 0.00 | 300 |  |  |
| tecnologia | string | 0.00 | 4 |  |  |
| mwh | double | 0.00 |  | 0.00 | 380.00 |
| archivo_origen | string | 0.00 | 53 |  |  |

## plants

300 filas · 2 columnas

| columna | tipo | % nulos | distintos | mínimo | máximo |
|---|---|---:|---:|---|---|
| central_codigo | string | 0.00 | 300 |  |  |
| tecnologia | string | 0.00 | 4 |  |  |

## plants_metadata

300 filas · 18 columnas

| columna | tipo | % nulos | distintos | mínimo | máximo |
|---|---|---:|---:|---|---|
| central_codigo | string | 0.00 | 300 |  |  |
| cen_id | int32 | 0.00 | 210 | 5 | 2379 |
| cen_nombre | string | 0.00 | 210 |  |  |
| match_metodo | string | 0.00 | 5 |  |  |
| region | string | 0.00 | 14 |  |  |
| provincia | string | 0.00 | 34 |  |  |
| comuna | string | 0.00 | 62 |  |  |
| latitud | double | 0.00 |  | -42.27 | -18.37 |
| longitud | double | 0.00 |  | -73.94 | -68.56 |
| potencia_mw | double | 0.00 |  | 0.29 | 690.12 |
| fecha_operacion | date32[day] | 3.00 |  | 1909-07-31 | 2026-03-23 |
| propietario | string | 0.00 | 128 |  |  |
| coordinado | string | 0.00 | 105 |  |  |
| estado | string | 0.00 | 3 |  |  |
| tipo_tecnologia | string | 0.00 | 5 |  |  |
| tipo_conv_energia | string | 0.00 | 3 |  |  |
| punto_conexion | string | 0.00 | 197 |  |  |
| conv_ernc | string | 0.00 | 2 |  |  |

## Curtailment: unidad y contraste con lo publicado

| tabla | suma mwh | % filas en cero | centrales | pares central-tecnología | máx. diario / (potencia × 24 h) |
|---|---:|---:|---:|---:|---:|
| curtailment_daily | 19,030,463.14 | 49.8 | 300 | 312 | 2.47 |
| curtailment_hourly | 18,982,205.91 | 83.6 | 300 | 312 | 1.95 |

- Suma diaria publicada en el diccionario: 19,030,463.14 MWh. Diferencia con la calculada: 0.00 MWh.
- Unidad: si `mwh` estuviera en kWh, el cociente contra la capacidad instalada rondaría 1.000. El máximo es 2.47, lo que confirma que la unidad es MWh.
- Hay 3 centrales con días en que el curtailment supera su potencia × 24 h, algo físicamente imposible. Lo más probable es que la potencia del catálogo no corresponda a la unidad que reporta el CEN. Hay que revisarlo en el Sprint 2.

| central | potencia_mw | match_metodo | días sobre capacidad | máx. mwh diario | máx. cociente |
|---|---:|---|---:|---:|---:|
| PFV-PUERTOSECO | 9.00 | contenido | 35 | 533.75 | 2.47 |
| PE-ANTOFAGASTA | 7.00 | exacto | 2 | 314.84 | 1.87 |
| PE-CANELA-2 | 18.15 | sin_unidad | 1 | 457.77 | 1.05 |
