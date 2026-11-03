# Fuentes de datos

Qué sirve de cada fuente para responder las preguntas del proyecto y qué se puede usar como variable de predicción sin fuga de información.

Revisado el 2026-11-03.

## Regla para clasificar variables

Una variable entra al modelo **como predictor** solo si se conoce **antes** del período que se predice.

- **Previa (P):** publicada antes del día o la hora objetivo (programas, pronósticos, catálogos). Puede usarse directamente.
- **Observada (O):** se mide durante el período o después (generación real, costo marginal real, clima observado). Solo sirve para análisis, para construir la variable objetivo o como **rezago** (por ejemplo, el valor de ayer).

---

## 1. Zenodo: dataset consolidado de curtailment (ya descargado)

- Registro `21652187`, versión 1.1, licencia CC BY 4.0. Hay que citar a Reyes Cerda y Cea Morales (DOI `10.5281/zenodo.21652187`).
- Período: 2022-01-01 a 2026-05-31, sin días faltantes. 300 centrales: 75 solares, 56 eólicas, 140 hidro de pasada y 29 hidro de embalse.
- Los ceros son explícitos: `mwh = 0` significa "sin curtailment", no un dato faltante.
- Las hidro tienen datos desde 2024-06 (serie diaria) y 2024-07 (horaria). Antes no hay curtailment hidro, pero no es lo mismo que cero: **no rellenar con ceros**.
- Hora en convención CEN 1–24: la hora `h` cubre el intervalo que **termina** en `h:00`.
- 12 centrales hidro cambian de etiqueta entre pasada y embalse según el reporte. `plants` tiene la tecnología canónica.
- `plants_metadata` trae `latitud`, `longitud` y `potencia_mw`, que se usan para cruzar con el clima y para normalizar el curtailment por capacidad.
- Archivos que no se descargaron y podrían servir más adelante: `errata_log.csv` (las 7 erratas de la fuente) y `CHECKSUMS.sha256` (SHA-256 oficiales para el manifiesto).

---

## 2. Coordinador Eléctrico Nacional: SIP público

Documentación: <https://portal.api.coordinador.cl/documentacion?service=sipubv2> · Especificación OpenAPI: `https://portal.api.coordinador.cl/swagger/spec/sip.json`

### Acceso

- **Necesita una API key**, que se envía como parámetro `user_key` en la URL: `https://sipub.api.coordinador.cl/<endpoint>?user_key=<API_KEY>`. Se pide en el portal o a la mesa de ayuda del CEN. Va en `.env`, nunca en Git.
- **El certificado TLS falla en Python** (`CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`): el servidor no envía la cadena intermedia y `certifi` no la tiene. **No desactivar la verificación** (`verify=False`). Opciones: el paquete `truststore` (usa el almacén de certificados de Windows) o agregar el certificado intermedio al bundle.
- La paginación no es uniforme. Por ejemplo, `generacion-real/v3` usa `page` desde 1 con `pageSize`, y `costo-marginal-real/v4` usa `page` desde 0 con `limit`. Hay que revisarla en cada endpoint.
- Los endpoints `/api/v2/recursos/...` solo funcionaron hasta el 31-12-2024, y los marcados "No vigente" están obsoletos. No usar ninguno de los dos.
- Pendiente de verificar con la key: desde qué fecha tiene historia cada endpoint y el tamaño máximo de página.

### Endpoints útiles

| Prioridad | Endpoint | Tipo | Para qué sirve | Campos clave |
|---|---|---|---|---|
| Alta | `/pronostico-erv/v4/findByDate` | P | Pronóstico oficial de generación solar y eólica por central, con cuantiles. Es el mejor predictor candidato: la diferencia entre lo pronosticado y lo generado aproxima la energía reducida. | `nombre_central`, `tipo_tecnologia`, `fecha_desde`, `fecha_hasta`, `fecha_reg_pronostico_coordinado`, `potencia_activa_horaria_25/50/75`, `velocidad_viento`, `temperatura` |
| Alta | `/generacion-real/v3/findByDate` | O | Generación real por central. Permite calcular la tasa de curtailment (energía reducida / energía posible). Filtra por `tipoTecnologia` e `idCentral`. | contenido paginado: revisar el esquema con la key |
| Alta | `/costo-marginal-real/v4/findByDate` | O | Costo marginal por barra. Un costo marginal cercano a cero en horas solares es una señal típica de curtailment por exceso de oferta. Usar `type=DEFINITIVO` para entrenar. | `barra_transf`, `fecha_hora`, `cmg_kwh_` |
| Alta | `/limitaciones-transmision/v4/findByDate` | O / P | Restricciones de la red, la causa principal del curtailment en el norte. Las que tienen `fecha_retorno_estimada` registrada antes del día objetivo son previas. | `sub_estacion`, `elemento_a_trabajar`, `potencia`, `fecha_perturbacion`, `fecha_retorno_estimada`, `fecha_efectiva_retorno`, `created` |
| Alta | `/demanda-neta/v4/findByDate` | O | Demanda neta del sistema por hora y generación renovable variable total. Una demanda baja con mucha energía renovable implica más riesgo de curtailment. | `fecha_hora`, `hora`, `demanda_neta_mwh`, `gen_erv_mwh`, `gen_bruta_mwh` |
| Media | `/generacion-programada-pcp/v4/findByDate` | P | Despacho programado del día siguiente por central (PCP). | `fecha_programa`, `fecha_hora`, `id_central`, `gen_programada_mw`, `capacidad_disponible_mw`, `barra` |
| Media | `/demanda-programada-pcp/v4/findByDate` | P | Demanda programada del día siguiente. | revisar esquema |
| Media | `/cmg-programado-pcp/v4/findByDate` | P | Costo marginal programado. Si se programa un costo marginal cero, se anticipa curtailment. | revisar esquema |
| Media | `/programas-mantenimiento-mayor/v4/findByDate` | P | Mantenimientos planificados que reducen la capacidad de transmisión. | revisar esquema |
| Media | `/instrucciones-operacionales-cmg/v4/findByDate` | O | Instrucciones del CEN a las centrales; el campo `motivo` puede explicar reducciones. | `central`, `fecha`, `hora`, `instruccion_cmg`, `motivo`, `consigna` |
| Media | `/pronostico-centrales-pasada/v4/findByDate` | P | Pronóstico de generación de las hidro de pasada. | `id_central`, `fecha_prevision`, `fecha_hora`, `energia_mwh` |
| Baja | `/centrales/v4/findByDate`, `/capacidad-instalada/v4/findByDate` | P | Catálogo y capacidad por central. Ya está casi todo en `plants_metadata`; sirve para validar y para el campo `id_central`. | `id_central`, `central`, `pot_max_bruta`, `region` |

**Descartados:** costo marginal online y proyectado, cargos de distribución, transferencias económicas, transformadores, sistemas medianos (Punta Arenas y Hornopirén no son parte del SEN), stock de combustibles, potencia SCADA por unidad (demasiado volumen para lo que aporta), índices de continuidad y de desempeño.

### Problema por resolver: unir las fuentes

El dataset de Zenodo usa `central_codigo` (nomenclatura del reporte de reducciones) y `cen_id` (catálogo Infotécnica). Los endpoints del CEN usan `id_central`, `nombre_central` o `llave_gen`. Antes de integrar, hay que verificar que `cen_id` coincida con `id_central` y documentar cómo se cruzan.

---

## 3. Open-Meteo

Documentación: <https://open-meteo.com/en/docs/historical-weather-api>

### Acceso

- Sin API key. Uso no comercial gratuito, con un límite de menos de 10.000 llamadas al día. Las consultas con muchas variables, días o coordenadas cuentan como varias llamadas, así que conviene agruparlas y guardar en caché.
- Se pueden pedir varias coordenadas en una sola llamada (`latitude=a,b&longitude=c,d`).
- Las centrales cercanas caen en la misma celda de la grilla: **deduplicar por celda** antes de consultar, en vez de hacer 300 llamadas.
- Al publicar algo con estos datos hay que citar a Open-Meteo y la fuente (ERA5 o IFS). Las referencias están al final de su página.

### Dos APIs, para dos usos distintos

| API | URL base | Qué entrega | Uso en el proyecto |
|---|---|---|---|
| **Historical Weather** | `https://archive-api.open-meteo.com/v1/archive` | Reanálisis: el clima que **ocurrió** (ERA5, ERA5-Land, ECMWF IFS 9 km). | **O.** Análisis exploratorio y para explicar el curtailment. **No** usar como predictor directo. |
| **Historical Forecast** | `https://historical-forecast-api.open-meteo.com/v1/forecast` | Pronósticos que se **emitieron** en su momento, guardados. Comprobado que hay datos desde al menos 2021-06. | **P.** Son los predictores correctos: en producción solo vas a tener pronósticos, así que hay que entrenar con pronósticos. |

Si entrenas con reanálisis y en producción predices con pronósticos, el modelo se ve mejor en la evaluación de lo que va a funcionar en la realidad. Es una fuga de información sutil y una buena pregunta de entrevista. Open-Meteo también tiene la **Previous Model Runs API**, con pronósticos a horizontes fijos de 1 a 7 días, útil si se define un horizonte de predicción concreto en el Sprint 5.

### Variables útiles

| Tecnología | Horarias | Diarias |
|---|---|---|
| Solar | `shortwave_radiation` (GHI), `direct_normal_irradiance`, `diffuse_radiation`, `cloud_cover`, `temperature_2m` (la eficiencia de los paneles cae con el calor) | `shortwave_radiation_sum`, `sunshine_duration` |
| Eólica | `wind_speed_100m` (altura de buje, mejor que 10 m), `wind_direction_100m`, `wind_gusts_10m` | `wind_speed_10m_max`, `wind_gusts_10m_max` |
| Hidro | `precipitation`, `snowfall`, `snow_depth` (solo ERA5-Land), `temperature_2m` (deshielo) | `precipitation_sum`, `snowfall_sum`, `et0_fao_evapotranspiration` |

**Descartadas:** temperatura y humedad del suelo, punto de rocío, presión, `weather_code` y temperatura aparente. No aportan a ninguna de las preguntas del proyecto.

### Detalles que hay que cuidar

- **Zona horaria:** el parámetro `timezone` usa un único desfase para todo el rango y **ignora el horario de verano**, y Chile cambia de hora dos veces al año. Hay que pedir `timeformat=unixtime` (UTC) y convertir a `America/Santiago` en el código. El CEN informa en hora local con convención 1–24.
- **Alineación horaria:** la radiación y la precipitación son el promedio o la suma de la **hora anterior**, lo que coincide con la convención del CEN (la hora `h` termina en `h:00`). El viento y la temperatura son **instantáneos** a esa hora.
- **Unidades:** el viento viene en km/h por defecto. Para energía eólica conviene pedir `wind_speed_unit=ms`.
- **Modelo fijo:** fijar `models=` explícitamente (por ejemplo `era5` o `ecmwf_ifs`) en vez del "best match" por defecto, para que el resultado sea reproducible y no cambie con las actualizaciones de Open-Meteo.
- Las coordenadas que devuelve la respuesta son las del **centro de la celda**, no las de la central. Hay que guardar ambas.

---

## Orden sugerido de incorporación

1. **Open-Meteo Historical Forecast** para las centrales solares y eólicas: no necesita key y aporta los predictores más directos.
2. **CEN `pronostico-erv` y `demanda-neta`:** primero hay que resolver la API key y el certificado.
3. **CEN `limitaciones-transmision` y `costo-marginal-real`:** las causas del curtailment.
4. **Open-Meteo Historical Weather:** para el análisis exploratorio del Sprint 2.
5. El resto de endpoints de prioridad media, solo si el análisis muestra que aportan.
