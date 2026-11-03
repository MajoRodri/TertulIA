# Métricas comparativas: TertulIA vs. chat normal

**Responsable:** Yohanna · **Issue:** #28 · **Revisión:** Helen  
**Fecha prevista de evaluación:** 3 de noviembre de 2026, tras la congelación de funcionalidades.

> **Principio de evaluación:** no se anticipan resultados. Regla del tribunal: «nada de cifras de memoria». Este documento solo contendrá números que hayamos **medido nosotras** o que tengan **fuente citada**, acompañados de evidencias. Hasta que se mida, las tablas quedan vacías: no se rellenan con estimaciones ni se presentan estimaciones como mediciones reales.

## 1. Objetivo

Evaluar si TertulIA ofrece mejoras respecto a una consulta realizada en un chat convencional para estudiar la viabilidad de un negocio local. En concreto, comprobar si aporta lo que un chat normal no: fuentes verificables, cálculos reproducibles (código o herramienta), revisión del Revisor, semáforo con confianza y aprobación humana. Por separado, se comprobarán las cifras del dossier (ver sección 9).

Se evaluarán cinco dimensiones comparables:

1. Calidad y fiabilidad de la información.
2. Verificabilidad de fuentes y afirmaciones.
3. Reproducibilidad de cálculos.
4. Calidad y utilidad del resultado.
5. Tiempo y recursos necesarios.

Por separado se medirán capacidades propias de TertulIA: investigación MCP, colaboración entre agentes, revisión, trazabilidad, intervención humana y generación del PDF. Las capacidades exclusivas no se utilizarán para penalizar al chat normal.

## 2. Sistemas comparados

### A. Chat normal
- Consulta a un modelo convencional, sin herramientas externas ni servidores MCP.
- Sin acceso a las fuentes de datos de TertulIA.
- Sin agentes especializados ni ciclo de revisión.
- Una única respuesta al encargo, sin repreguntas (una sola pasada).

### B. TertulIA
Cinco agentes coordinados por el grafo, en este orden: Investigador (`researcher`) → Visión (`vision`) → Analista (`analyst`) → Redactor (`writer`) → Revisor (`reviewer`).

- Investigación mediante herramientas MCP (servidor propio `neighbourhood_data` y servidor `fetch`).
- Análisis de datos y cálculos con herramientas especializadas (punto de equilibrio y ejecución de código).
- Análisis de imágenes cuando se aporten fotografías.
- Redacción mediante el Redactor y revisión mediante el Revisor, con posibles rondas de corrección (máximo 3).
- Generación de veredicto y semáforo de confianza.
- Aprobación o rechazo humano y generación del PDF final.

## 3. Protocolo de evaluación

1. **Encargo común:** sector `cafe_cowork`, barrio Atocha, presupuesto y perfil `analista`. Fijar el texto exacto **antes de iniciar** y guardarlo en este documento.
2. **Chat normal:** realizar una consulta sin herramientas externas y guardar la respuesta íntegra en `docs/metricas/chat_normal.md`.
3. **TertulIA:** ejecutar el flujo completo desde la interfaz y conservar informe, fuentes y trazas (`outputs/` y `trazas/`) resumidos en `docs/metricas/tertulia.md`.
4. **Modelo:** utilizar el mismo modelo base siempre que sea posible (decisión en `docs/decisiones/0001-modelo-y-claves.md`). Registrar el modelo y la configuración de cada agente y del chat normal.
5. **Repeticiones:** realizar tres ejecuciones independientes por sistema y registrar los tres resultados (el modelo varía entre ejecuciones).
6. **Evaluación ciega:** presentar los resultados sin identificar el sistema y aplicar la misma rúbrica. **Puntúa otra persona**, no la que lanzó la prueba.
7. **Conservación:** guardar también las ejecuciones fallidas, incompletas o degradadas.
8. **Registro:** anotar fecha, hora, duración, modelo, configuración, incidencias y modo de ejecución.

**Condiciones especiales**
- Identificar y excluir de la comparación principal las ejecuciones simuladas.
- Diferenciar datos obtenidos en directo, desde caché y en modo demo (`DEMO_MODE`, que activa una persona antes de arrancar).
- Foursquare solo se consulta en directo (sus términos no permiten guardar sus datos): las ejecuciones en caché o en modo demo no lo incluyen y, por tanto, no son directamente comparables con las ejecuciones en directo.
- Evaluar las pruebas con imágenes en un bloque separado.
- Conservar y contabilizar las ejecuciones fallidas.

## 4. Métricas comparativas principales

| Métrica | Cómo se mide | Chat normal | TertulIA |
|---|---|---|---|
| Afirmaciones respaldadas | Afirmaciones con evidencia verificable / total de afirmaciones factuales | | |
| Fuentes verificables | Fuentes existentes que respaldan lo afirmado (se abren una a una, con enlace y fecha) / total de fuentes citadas | | |
| Cifras sin respaldo | Cifras sin fuente, dato de entrada o cálculo reproducible | | |
| Exactitud de los datos | Datos correctos frente a un conjunto de referencia verificado previamente | | |
| Cálculos reproducibles | Cálculos que pueden repetirse con el código o la herramienta registrados y los mismos valores de entrada | | |
| Datos ausentes declarados | Casos de «sin dato» señalados frente a inventados | | |
| Coherencia del informe | Correspondencia entre datos, análisis, conclusiones y recomendación | | |
| Tiempo hasta el informe | Minutos, con cronómetro, desde el inicio hasta disponer del resultado evaluable | | |
| Consumo de tokens | Tokens de entrada y salida: de `trazas/` en TertulIA y de la API en el chat normal, cuando estén disponibles | | |
| Coste de ejecución | Coste real de llamadas al modelo y servicios externos, si puede calcularse | | |
| Revisión humana posible | ¿Hay un punto de aprobación antes de entregar el informe? Sí / no | | |

Las fuentes deben respaldar realmente lo afirmado, no limitarse a aparecer como enlaces. La exactitud se contrastará con datos de referencia; los cálculos se repetirán con los mismos valores. Declarar correctamente que un dato no está disponible no se considerará un error.

## 5. Métricas específicas de TertulIA

Estas métricas evalúan el funcionamiento de las integraciones y capacidades propias del proyecto. No son comparaciones directas con el chat normal.

### 5.1. Investigación MCP y trazabilidad

**Objetivo:** comprobar que los datos del informe proceden de las herramientas y fuentes correspondientes.

| Indicador | Cómo se mide | Resultado |
|---|---|---|
| Fuentes registradas | Número de fuentes incorporadas a la ejecución | |
| Hallazgos trazables | Hallazgos vinculados a sus fuentes mediante `source_ids` o al cálculo que los produjo mediante `code_ref` | |
| Datos directos y caché | Identificación del origen (`from_cache`) y de la fecha de recuperación (`retrieved_at`) | |
| Datos en modo demo | Identificación de ejecuciones con datos guardados | |
| Afirmaciones verificables | Afirmaciones rastreables hasta su evidencia | |

Detalle de fuentes, caché, modo demo y atribución: `docs/fuentes-de-datos.md`.

### 5.2. Colaboración entre agentes y revisión del Revisor

**Objetivo:** evaluar si la colaboración entre agentes mejora la calidad del informe. El Redactor escribe; el Revisor analiza el borrador y puede devolver observaciones que den lugar a nuevas rondas, hasta un máximo de 3 (`MAX_ITERATIONS`).

| Indicador | Cómo se mide | Resultado |
|---|---|---|
| Revisiones ejecutadas | Número de ejecuciones del Revisor | |
| Observaciones detectadas | Número de observaciones emitidas | |
| Observaciones justificadas | Observaciones respaldadas por datos o evidencias | |
| Correcciones aplicadas | Observaciones reflejadas correctamente en la siguiente versión | |
| Discrepancias detectadas | Diferencias entre borrador e investigación o cálculos | |
| Rondas de revisión | Número de rondas hasta el resultado final | |
| Tope de rondas alcanzado | Ejecuciones que llegan al máximo sin aprobación del Revisor (pasan a aprobación humana con aviso) | |
| Revisor disponible | Ejecuciones finalizadas correctamente frente a fallidas | |

Más rondas no equivalen necesariamente a mejor calidad: se evaluará si las observaciones son correctas y si las correcciones mejoran el resultado.

### 5.3. Uso de `mcp_research_summary`

**Objetivo:** comprobar que la información de investigación MCP llega al Revisor y se utiliza para contrastar las afirmaciones. Implementación relacionada: `main.py`, `state.py`, `nodes.py` y `tasks.yaml`.

| Indicador | Cómo se mide | Resultado |
|---|---|---|
| Resumen recibido | Confirmación de que `mcp_research_summary` llega al flujo del Revisor | |
| Uso verificable | Evidencia en logs, trazas o resultado de revisión de que se ha utilizado | |
| Cifras contrastadas | Número de cifras revisadas con información del resumen | |
| Discrepancias detectadas | Diferencias identificadas entre borrador y datos de investigación | |

Recibir el resumen no demuestra por sí solo que se haya utilizado correctamente. Se necesita evidencia del contraste realizado.

### 5.4. Visión artificial y análisis de imágenes

**Objetivo:** evaluar el análisis visual cuando se incorporan fotografías de locales o cartas. Se realizará aparte de la comparación principal, porque el chat normal no necesariamente dispone de la misma herramienta.

| Indicador | Cómo se mide | Resultado |
|---|---|---|
| Imágenes analizadas | Número de imágenes procesadas correctamente | |
| Observaciones obtenidas | Número de observaciones generadas por el agente de visión | |
| Confianza de observaciones | Clasificación de confianza alta, media o baja | |
| Precios extraídos | Precios identificados (tabla Producto / Tamaño / Precio) y comprobados frente a la imagen | |
| Observaciones verificadas | Observaciones que coinciden con la evidencia visual | |
| Errores de análisis | Imágenes rechazadas, análisis fallidos o clasificaciones incorrectas | |

### 5.5. Consumo de tokens en visión

**Objetivo:** comprobar el consumo de tokens de `vision_charts_node` cuando el proveedor devuelve esa información. La implementación consulta `llm.token_usage` antes y después de `analyse_image` y suma la diferencia a `state["tokens_used"]`.

| Indicador | Cómo se mide | Resultado |
|---|---|---|
| Tokens antes del análisis | Valor registrado antes de `analyse_image` | |
| Tokens después del análisis | Valor registrado después de `analyse_image` | |
| Diferencia de tokens | Diferencia entre ambos valores, si está disponible | |
| Integración en el contador | Comprobar actualización de `state["tokens_used"]` | |
| Disponibilidad del dato | Indicar si el proveedor devuelve información de consumo | |

Si el proveedor no devuelve el consumo, se registrará como **no disponible**. Un contador sin incremento no demuestra que el análisis haya consumido cero tokens. Se comprobará por separado si el contador global recoge todas las llamadas de CrewAI. El presupuesto por informe es `MAX_TOKENS_PER_REPORT`: si se agota, el flujo se detiene y decide la persona (ERR-006).

### 5.6. Veredicto y semáforo de confianza

**Objetivo:** comprobar la coherencia entre investigación, cálculos, observaciones del Revisor y recomendación final.

| Indicador | Cómo se mide | Resultado |
|---|---|---|
| Veredicto generado | Ejecuciones que generan un veredicto real | |
| Semáforo coherente | Correspondencia entre datos y nivel de recomendación | |
| Confianza justificada | Correspondencia entre confianza asignada y evidencia disponible (la confianza baja con cada dato que falta) | |
| Contexto incorporado | Comprobar si el contexto del usuario se refleja en revisión y veredicto | |
| Veredicto degradado | Casos en que incidencias impiden una recomendación completa | |

El veredicto se evaluará frente a una rúbrica común; no se considerará correcto únicamente porque el sistema haya generado un semáforo.

### 5.7. Aprobación humana y generación del informe

**Objetivo:** comprobar que la decisión final permanece bajo control humano y que el PDF refleja el resultado aprobado.

| Indicador | Cómo se mide | Resultado |
|---|---|---|
| Decisiones registradas | Aprobaciones y rechazos identificados en las trazas | |
| Aprobación previa al PDF | Comprobar que el PDF solo se genera después de la aprobación | |
| PDF generado | Número de informes finales generados correctamente | |
| Coherencia del PDF | Correspondencia entre PDF, datos, fuentes y veredicto | |
| Rechazos respetados | Comprobar que un rechazo no genera un informe aprobado | |
| Caducidad sin respuesta | Estudios que caducan por falta de decisión humana y no se aprueban solos (ERR-009) | |

Esta funcionalidad se medirá como capacidad propia de TertulIA, no como métrica equivalente del chat normal.

## 6. Fiabilidad de las ejecuciones

| Indicador | Cómo se mide | Resultado |
|---|---|---|
| Ejecuciones completas | Ejecuciones que llegan al resultado esperado | |
| Ejecuciones fallidas | Ejecuciones que no completan el flujo | |
| Errores por ejecución | Número y tipo de errores registrados (códigos ERR-XXX) | |
| Reintentos | Número de reintentos realizados | |
| Degradaciones | Casos en que una fuente o herramienta no está disponible y el flujo continúa parcialmente | |
| Tiempo de recuperación | Tiempo para recuperarse de una incidencia, cuando pueda medirse | |

El detalle de códigos de error, severidades y comportamiento se mantiene en `docs/errores.md`.

## 7. Rúbrica de evaluación ciega

| Puntuación | Criterio |
|---|---|
| 0 | Información incorrecta, inventada o sin respaldo suficiente |
| 1 | Información parcialmente correcta, pero con errores importantes |
| 2 | Información correcta en general, con algunas carencias |
| 3 | Información correcta, verificable y bien justificada |

Se aplicará a calidad de investigación, fiabilidad de afirmaciones, exactitud de cálculos, coherencia del análisis, calidad de conclusiones y utilidad de la recomendación final. Las capacidades exclusivas de TertulIA se evaluarán en sus indicadores específicos.

## 8. Registro de ejecuciones

| Fecha | Sistema | Modelo | Modo de datos | Ejecución | Duración | Estado | Quién puntúa | Evidencia |
|---|---|---|---|---|---|---|---|---|
| | Chat normal | | No aplica | 1 | | | | |
| | Chat normal | | No aplica | 2 | | | | |
| | Chat normal | | No aplica | 3 | | | | |
| | TertulIA | | Directo / caché / demo | 1 | | | | |
| | TertulIA | | Directo / caché / demo | 2 | | | | |
| | TertulIA | | Directo / caché / demo | 3 | | | | |

Cada ejecución deberá conservar: prompt original; respuesta o informe completo; modelo y configuración; fuentes y hallazgos; trazas; observaciones y correcciones del Revisor; veredicto y decisión humana; tokens y tiempos disponibles; errores e incidencias; y puntuación de evaluación ciega. No se incluirán claves API, credenciales ni datos personales.

## 9. Cifras del dossier a respaldar

| Cifra | ¿Medida o citada? | Fuente / medición | Estado |
|---|---|---|---|
| «3 semanas» (estudio manual) | | | pendiente |
| «más de 1.000 €» (estudio manual) | | | pendiente |

Si no se consigue fuente o medición, **se quita la cifra del dossier** o se reformula sin número.

## 10. Documentación relacionada

| Tema | Documento |
|---|---|
| Fuentes MCP, caché, datos directos y demo | `docs/fuentes-de-datos.md` |
| Ética, decisiones humanas, descartes y guardrails | `docs/etica-y-gobernanza.md` |
| Errores, reintentos y degradaciones | `docs/errores.md` |
| Modelo y claves | `docs/decisiones/0001-modelo-y-claves.md` |
| Proceso y decisiones de CrewAI | `docs/decisiones/0002-proceso-crewai.md` |
| Contratos y estructuras de datos | `src/tertulia/schemas/` |

## 11. Limitaciones

Se escribirán tal cual en la presentación.

- Tres ejecuciones por sistema y un único caso de estudio constituyen una evaluación orientativa, no un estudio estadístico.
- Los modelos pueden variar sus respuestas incluso con el mismo prompt.
- La arquitectura multiagente de TertulIA implica más llamadas al modelo que una consulta convencional.
- Las herramientas externas pueden devolver datos diferentes según fecha y disponibilidad.
- La evaluación de calidad tiene un componente subjetivo; por eso se propone una rúbrica y evaluación ciega, y se publican las salidas.
- Los proveedores no siempre facilitan información completa sobre consumo de tokens.
- Los datos en caché y los obtenidos en directo no tienen necesariamente la misma actualidad.
- Los tests verifican comportamientos concretos del código, pero no demuestran por sí solos la calidad de todos los informes reales.
- Las funcionalidades exclusivas de TertulIA no deben interpretarse como una ventaja demostrada hasta evaluar su utilidad mediante evidencias.

**Conclusión esperada:** determinar con resultados verificables si TertulIA mejora la calidad, trazabilidad y utilidad de los estudios frente a una consulta convencional, y documentar qué aporta su arquitectura multiagente y su supervisión humana.
