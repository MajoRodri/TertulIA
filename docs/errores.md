# Política de errores de TertulIA

Documento de referencia del Issue #14. Explica qué errores puede producir el sistema, cómo se clasifican, qué hace con cada uno y dónde queda registrado.

> **Cómo leer este documento.** Describe la política diseñada y, junto a cada punto, **su estado en la entrega** (código de `dev` a 3 de noviembre de 2026):
> - **Implementado:** funciona en el flujo real.
> - **Parcial:** funciona en parte; se explica qué falta.
> - **Diseñado, no conectado:** el código existe y tiene tests, pero el flujo real todavía no lo usa.
>
> Lo que falta está en la sección [Limitaciones conocidas y trabajo futuro](#limitaciones-conocidas-y-trabajo-futuro).

## Principios

1. **Fail soft, no fail silent.** Un fallo de una herramienta no tumba el sistema, pero tampoco se oculta: se degrada, se registra y se sigue, o se para de forma controlada si es grave.
2. **Nada se inventa.** Si un dato no está, se dice «sin dato». Si una herramienta falla, se usa un respaldo (por ejemplo, datos guardados) y el informe indica de dónde sale cada dato.
3. **Todo error tiene un código.** Cada error lleva un código (`ERR-XXX`), el nodo que lo produjo y un detalle técnico.
4. **El humano decide en los casos límite.** Ante un error grave, el grafo deja de repetir y pasa a la aprobación humana.

## Taxonomía de errores

Cada error tiene un código y una severidad. La severidad define qué hace el grafo.

| Código | Nombre | Severidad | Qué significa | Comportamiento diseñado | Estado en la entrega |
|---|---|---|---|---|---|
| ERR-001 | `TOOL_TIMEOUT` | Degradable | Una herramienta externa no responde (MCP, API, code_exec) | Respaldo a datos guardados si existen; si no, «sin dato» y error registrado | **Parcial.** El respaldo funciona: si Overpass falla (429, 502), el servidor MCP usa las capturas guardadas e indica su fecha. El error no se registra como `ERR-001` |
| ERR-002 | `TOOL_FAILURE` | Degradable | La herramienta responde con error o con argumentos inválidos | Igual que ERR-001 | **Parcial.** Se registra en `vision_charts` si falla el análisis de un gráfico. Para las herramientas de los agentes, el agente recibe el error como texto, pero no se registra como `ERR-002` |
| ERR-003 | `MISSING_DATA` | Degradable | Un dato necesario no está | Dato marcado como «sin dato»; la confianza baja | **Parcial.** Los agentes escriben «sin dato» y el informe lo muestra en «Datos que faltan». No se registra como `ERR-003` |
| ERR-004 | `LLM_ERROR` | Degradable | El modelo falla o no responde | Reintento con espera creciente; si sigue fallando, error registrado | **Parcial.** Los reintentos están implementados en `crew.py` (5 intentos, espera de 5 a 60 s, 90 s por intento). No se registra como `ERR-004` |
| ERR-005 | `INVALID_OUTPUT` | Degradable | El modelo devuelve algo que no encaja con el esquema | Se descarta, se registra y el dato queda como «sin dato» | **Diseñado, no conectado** |
| ERR-006 | `TOKEN_BUDGET_EXHAUSTED` | **Fatal** | Se supera `MAX_TOKENS_PER_REPORT` | El grafo para y va a la aprobación humana sin veredicto | **Parcial.** Ver [Presupuesto de tokens](#presupuesto-de-tokens) |
| ERR-007 | `MAX_ITERATIONS_REACHED` | Degradable | El bucle de revisión llega al límite sin aprobación | Aviso registrado; el grafo pasa a la aprobación | **Parcial.** El límite de 3 rondas funciona (`MAX_ITERATIONS`). El aviso `ERR-007` no se registra |
| ERR-008 | `GRAPH_INTERNAL` | **Fatal** | Un nodo lanza una excepción no controlada | Se captura, se registra y el grafo va a la aprobación | **Implementado** en los nodos que llaman al modelo (`writer`, `reviewer`, `vision_charts`) |
| ERR-009 | `HUMAN_TIMEOUT` | **Fatal** | La persona no responde a tiempo | El estudio caduca sin aprobarse | **Implementado.** Ver [Contrato de ERR-009](#contrato-de-err-009-con-la-api-timeout-humano) |

Nota: el rechazo humano **no es un error**. Es una decisión, y se registra como `TraceEntry` con `tool="ui.reject"` (Issue #13). `ERR-009` es distinto: es la ausencia de decisión.

## Comportamiento del grafo por severidad

- **Degradable:** el error se añade a `state["errors"]` y el flujo sigue con lo que haya.
- **Fatal:** el error se añade a `state["errors"]` y el grafo deja de repetir el bucle (`should_continue` en `edges.py`) y pasa directamente a la aprobación humana.
- **Nunca:** que un error tumbe el proceso. Los nodos que llaman al modelo convierten cualquier excepción en `ERR-008`. Los nodos `research` y `analyst` solo reciben datos ya calculados, así que no ejecutan nada que pueda fallar.
- **Tiempo límite por agente:** el Redactor y la Revisora del grafo tienen 180 s por paso (`_run_step_timeout` en `nodes.py`). Si se agota, se registra `ERR-008`.

## Dónde se producen los errores

En la entrega, la investigación, la visión y el análisis se ejecutan **en la API durante el debate**, y el grafo ejecuta al Redactor y a la Revisora (ver `docs/arquitectura.md`). Por eso los errores se gestionan en dos sitios:

| Dónde | Qué puede fallar | Cómo se gestiona hoy |
|---|---|---|
| Servidor MCP `neighbourhood_data` | Overpass o Foursquare no responden | Reintento y respaldo a capturas guardadas (`from_cache`, fecha de captura). Si no hay capturas, error `[source_unavailable]` |
| Agentes en la API (debate) | Herramienta con error, modelo que no responde | El agente recibe el error como texto y continúa; el modelo se reintenta en `crew.py`. Si falla un paso entero, la interfaz muestra un mensaje marcado como «ejemplo» |
| Nodos `writer` y `reviewer` del grafo | Modelo, tiempo límite, presupuesto de tokens | `ERR-008` o `ERR-006` en `state["errors"]` |
| Nodo `vision_charts` | Gráfico ilegible o modelo que falla | `ERR-002` por gráfico, sin detener el resto |
| Nodo `human_approval` | La persona no responde | `ERR-009` (ver el contrato más abajo) |

## Representación en el estado, el veredicto y el informe

| Dónde | Diseño | Estado en la entrega |
|---|---|---|
| `state["errors"]` | Lista de `ErrorEntry` (`src/tertulia/graph/errors.py`) con código, nodo, severidad, mensaje y detalle | **Implementado** para los errores del grafo |
| `Verdict.warnings` | Un aviso por cada error degradable que afecte al veredicto | **Diseñado, no conectado:** el veredicto se construye a partir del borrador del Redactor y no incluye avisos |
| `Verdict.missing_data` | Los datos marcados como «sin dato» | **Diseñado, no conectado.** Los datos que faltan aparecen en el texto del informe («Datos que faltan»), no en este campo |
| Informe PDF, sección «Incidencias» | Errores y su impacto | **No existe** en la plantilla actual |
| `TraceEntry.error` | Detalle del error de herramienta en la traza | **Diseñado, no conectado:** las trazas registran hoy la decisión humana |

Ejemplo de `ErrorEntry`:

```python
ErrorEntry(
    code="ERR-008",
    node="reviewer",
    severity=ErrorSeverity.FATAL,
    message="Error interno en el nodo reviewer. El estudio se detiene.",
    technical_detail="TimeoutError: El agente 'review' no respondió en 180 s",
    retryable=False,
)
```

## Códigos del servidor MCP y su mapeo

El servidor de datos locales (`src/tertulia/mcp/servers/neighbourhood_data/server.py`) pone un código entre corchetes al principio de sus mensajes de error:

| Código del servidor | Significado | `ERR-XXX` previsto | Severidad |
|---|---|---|---|
| `[invalid_input]` | Argumentos inválidos (barrio inexistente, categoría no válida, radio fuera de rango) | `ERR-002` | Degradable |
| `[not_found]` | No hay datos para ese barrio o categoría | `ERR-003` | Degradable |
| `[source_unavailable]` | Overpass caído y sin datos guardados | `ERR-001` | Degradable |

El mapeo está implementado y probado: `error_code()` en `src/tertulia/mcp/client.py` y `_mcp_event_to_error()` en `src/tertulia/graph/tool_events.py` (10 tests). MCP antepone `"Error executing tool <name>: "` al mensaje, así que `error_code()` busca el código en cualquier parte del texto.

**Estado en la entrega: diseñado, no conectado.** La captura de eventos (`capture_tool_events()`) no se usa todavía en el flujo real, así que estos errores no llegan a `state["errors"]`.

CrewAI valida los argumentos de las herramientas **antes** de llamar al MCP. Si no son válidos (por ejemplo, `radius_m="lejos"`), emite `ToolValidateInputErrorEvent` en lugar de `MCPToolExecutionFailedEvent`. El mapeo también lo contempla y lo convierte en `ERR-002` recuperable.

## Presupuesto de tokens

**Lo que funciona:**

- Cada paso del crew devuelve los tokens reales que ha gastado (`CrewOutput.token_usage.total_tokens`, en `crew.py`).
- La API los suma durante el debate, y los nodos `writer` y `reviewer` suman los del bucle de revisión. El total se muestra en el veredicto y en el pie del PDF.
- Antes de llamar al modelo, cada nodo del grafo comprueba si `tokens_used >= MAX_TOKENS_PER_REPORT` (500.000 por defecto). Si es así, no llama, registra `ERR-006` y el grafo va a la aprobación humana.

**Lo que no funciona como estaba diseñado:**

- Los pasos del debate, que se ejecutan en la API, **no comprueban el presupuesto** antes de llamar al modelo.
- Con `ERR-006`, la persona **sigue viendo un veredicto y puede generar el PDF**: el veredicto se construye a partir del borrador y nunca es `None`, que es lo que la API comprueba para bloquear el informe.

Como referencia, un estudio completo medido el 3 de noviembre consumió 118.252 tokens (unos 104.000 en el debate y el resto en el bucle de revisión), muy por debajo del límite.

## Contrato de ERR-009 con la API (timeout humano)

**Estado en la entrega: implementado.**

El grafo pausado en `interrupt_before=["human_approval"]` no tiene reloj interno: está esperando. Su estado se guarda en `checkpoints.db` (`SqliteSaver`). El temporizador vive en la API:

1. La API guarda la hora en que el estudio se pausó (`paused_at`).
2. Si `now - paused_at > settings.HUMAN_TIMEOUT_S` (24 h por defecto), la API reanuda el grafo con `{"expired": True}` y marca el estudio como `expired`.
3. El nodo `human_approval` lee `expired`, registra `ERR-009` en `errors` y un `TraceEntry` con `tool="ui.timeout"`, y termina con `human_approved=False`.
4. La API devuelve `{"ok": false, "reason": "estudio caducado"}` y no genera el PDF.

Estados del estudio (`job["status"]`):

| Estado | Cuándo | Qué muestra la interfaz |
|---|---|---|
| `running` | El debate se está ejecutando | Indicador de progreso de cada agente |
| `paused` | El grafo espera la decisión humana | Contexto, veredicto y botones de aprobar o rechazar |
| `done` | Aprobado y PDF generado | Descarga del informe |
| `rejected` | Rechazado por la persona | Vuelta al debate |
| `expired` | Caducado sin respuesta (`ERR-009`) | «Estudio caducado» (no es un fallo técnico) |
| `failed` | No hay veredicto al aprobar | «No se pudo generar el informe» con el motivo |

Limitación: `rejected` todavía no es definitivo en la API. Si la persona vuelve al paso 5 después de rechazar, puede aprobar y descargar el PDF (ver la sección siguiente).

## Limitaciones conocidas y trabajo futuro

| Limitación | Impacto | Qué haría falta | Piezas que ya existen |
|---|---|---|---|
| Los errores de herramientas (ERR-001 a 003) no llegan al estado | Los fallos de Overpass o Foursquare quedan en el log del servidor, no en el informe | Envolver los pasos del debate con `capture_tool_events()` y añadir los errores al estudio | `capture_tool_events()`, `convert_tool_events()`, `error_code()` y sus 10 tests |
| ERR-004, ERR-005 y ERR-007 no se registran | No hay constancia de reintentos del modelo, salidas inválidas ni de que el bucle llegó al límite | Registrar `ERR-007` en el nodo `reviewer` al agotar las rondas; `ERR-004` y `ERR-005` al conectar el crew en los nodos | Códigos definidos en `errors.py` |
| El presupuesto de tokens no bloquea el PDF | Con `ERR-006`, el informe se puede generar igualmente | Comprobar el presupuesto en los pasos del debate y bloquear la aprobación si hay errores fatales | `_tokens_exhausted()`, `ERR-006` |
| El veredicto no muestra avisos ni datos que faltan | La persona no ve los errores junto al semáforo | Rellenar `Verdict.warnings` y `missing_data` a partir de `state["errors"]` | Campos ya definidos en `schemas/models.py`; la interfaz ya sabe mostrarlos |
| Las trazas no incluyen errores | Un tercero no puede auditar qué falló | Guardar `state["errors"]` junto a las trazas y rellenar `TraceEntry.error` | `trace_from_execution()`, `trace_from_break_even()` |
| `rejected` no es definitivo | Un estudio rechazado se puede aprobar después | Comprobar `status == "rejected"` al inicio de `/api/approve` | Estado ya guardado en `_jobs` |

## Tests

| Archivo | Qué cubre |
|---|---|
| `tests/test_tool_events.py` | Mapeo de eventos MCP, de validación y de uso a `ErrorEntry` (10 tests) |
| `tests/test_errors.py` | Presupuesto de tokens (`ERR-006`), excepción interna (`ERR-008`), revisor que falla tratado como rechazo, acumulación de errores y caducidad (`ERR-009`) (10 tests) |
| `tests/test_graph_flow.py` | Flujo del grafo con aprobación humana: pausa, aprobación, rechazo y contexto del chat (5 tests) |

Limitación de los tests del grafo: los nodos `writer` y `reviewer` crean el modelo por dentro, así que en los tests no pueden llamar a un modelo falso. Por eso `test_graph_flow.py` comprueba el flujo por el camino del error (`ERR-008`), no un bucle de revisión real.
