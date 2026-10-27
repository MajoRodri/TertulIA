# Política de errores de TertulIA

Documento de referencia del Issue #14. Explica qué errores puede producir el grafo, cómo se clasifican, qué hace el sistema con cada uno y dónde queda registrado.

## Principios

1. **Fail soft, no fail silent.** El grafo no muere por un fallo de una herramienta, pero tampoco lo oculta. Degrada, registra y sigue, o se para de forma controlada si el fallo es fatal.
2. **Nada se inventa.** Si un dato no está, se marca como `missing` y baja la confianza. Si una herramienta falla, se registra el error y el informe lo dice.
3. **Todo error es trazable.** Cada error lleva un código, el nodo que lo produjo y un contexto. El informe y el log pueden mostrarlo.
4. **El humano decide en los casos límite.** Si el presupuesto de tokens se agota o hay demasiados errores, el grafo no decide solo: para y pasa a `human_approval` con un veredicto degradado.

## Taxonomía de errores

Cada error tiene un código (`ERR-XXX`) y una severidad. La severidad define qué hace el grafo.

| Código | Nombre | Severidad | Qué significa | Comportamiento |
|---|---|---|---|---|
| ERR-001 | `TOOL_TIMEOUT` | Degradable | Una herramienta externa no responde (MCP, API, code_exec) | Fallback a caché si existe; si no, dato `missing` y error registrado. El grafo sigue. |
| ERR-002 | `TOOL_FAILURE` | Degradable | La herramienta responde con error (excepción, 500, validación Pydantic, argumentos inválidos) | Igual que ERR-001. Si es `run_code`, se registra el `stderr` en el `TraceEntry`. |
| ERR-003 | `MISSING_DATA` | Degradable | Un dato necesario no está | `Finding` con `status=missing`, sin valor. `compute_confidence` resta la penalización. El grafo sigue. |
| ERR-004 | `LLM_ERROR` | Degradable | El LLM falla o devuelve algo inválido | Un reintento con backoff. Si vuelve a fallar, error registrado y el nodo devuelve lo que tenga (o vacío). El grafo sigue. |
| ERR-005 | `INVALID_OUTPUT` | Degradable | El LLM devuelve algo que no encaja con el esquema | Se descarta ese output, se registra el error y se marca el dato como `missing`. |
| ERR-006 | `TOKEN_BUDGET_EXHAUSTED` | **Fatal** | Se ha superado `MAX_TOKENS_PER_REPORT` | El grafo para, va a `human_approval` con `verdict=None` y un warning claro. |
| ERR-007 | `MAX_ITERATIONS_REACHED` | Degradable | El bucle de revisión llegó al límite sin aprobación del revisor | Se registra como warning, el grafo pasa a `human_approval` con `amber`. |
| ERR-008 | `GRAPH_INTERNAL` | **Fatal** | Un nodo lanza una excepción no controlada | Se captura en el borde del nodo, se registra y el grafo va a `human_approval` con `verdict=None`. |
| ERR-009 | `HUMAN_TIMEOUT` | **Fatal** | El humano no responde en un tiempo definido | El grafo termina sin aprobación. `human_approved=False`, `expired=True` y error registrado. La API marca el job como `expired`. |

Nota: el rechazo humano **no es un error**. Es una decisión. Se traza como `TraceEntry` con `tool="ui.reject"` (Issue #13). El `ERR-009` es distinto: es la ausencia de decisión.

## Comportamiento del grafo por severidad

- **Degradable:** el nodo captura el error, lo añade a `state["errors"]` y devuelve un estado parcial. El flujo sigue. El revisor puede ver los errores y rechazar si son graves.
- **Fatal:** el nodo captura el error, lo añade a `errors`, y el grafo termina en `human_approval` sin veredicto. El humano ve el error y decide si aprueba (sin PDF) o rechaza.
- **Nunca:** un error no controlado que tumbe el proceso. El borde de cada nodo tiene un `try/except` que convierte cualquier excepción en `ERR-008`.

## Matriz nodo → errores posibles → origen

| Nodo | Errores posibles | Cómo se capturan |
|---|---|---|
| `research` | `ERR-001`, `ERR-002`, `ERR-003` (MCP) | Event bus: `MCPToolExecutionFailedEvent`, `ToolValidateInputErrorEvent`, `ToolUsageErrorEvent` → `tool_events.py` |
| `research` | `ERR-004` (LLM) | `try/except` en el nodo |
| `analyst` | `ERR-002`, `ERR-003` (`run_code`, `break_even_tool`) | `try/except` en el nodo (las herramientas devuelven `ExecutionResult` o `{"status": "error"}`) |
| `analyst` | `ERR-005` (output inválido) | Validación Pydantic en el adaptador (`adapters.py`) |
| `writer` | `ERR-004`, `ERR-006` | `try/except` en el nodo + comprobación de tokens |
| `reviewer` | `ERR-004`, `ERR-007` | `try/except` en el nodo + `edges.py` |
| `human_approval` | `ERR-009` | La API reanuda el grafo con `{"expired": true}` cuando el job supera `HUMAN_TIMEOUT_S` |

## Representación en el estado, el veredicto y el informe

- **`state["errors"]`:** lista de `ErrorEntry` (ver `src/tertulia/graph/errors.py`). Ejemplo:

  ```python
  ErrorEntry(
      code="ERR-001",
      node="research",
      severity=ErrorSeverity.DEGRADABLE,
      message="La fuente de datos no responde. Se usan datos guardados si están disponibles.",
      technical_detail="Overpass timeout tras 30 s; fallback a caché (from_cache=True).",
      retryable=True,
  )
  ```

- **`Verdict.warnings`:** una entrada por cada error degradable que afecte al veredicto. Ejemplo: `"3 datos no encontrados; confianza reducida"`.
- **`Verdict.missing_data`:** se rellena con los `Finding` con `status=missing`.
- **Informe:** una sección «Incidencias» con los errores y su impacto. El analista lo ve en el PDF.
- **`TraceEntry.error`:** para los errores de herramienta (`ERR-001`, `ERR-002`, `ERR-008`), se rellena el campo `error` del `TraceEntry` correspondiente (Issue #16).

## Códigos del servidor MCP y su mapeo

El servidor de datos locales (`src/tertulia/mcp/servers/neighbourhood_data/server.py`) pone un código entre corchetes al principio de sus mensajes de error:

| Código del servidor | Significado | `ERR-XXX` | Severidad |
|---|---|---|---|
| `[invalid_input]` | Argumentos inválidos (barrio inexistente, categoría no válida, radio fuera de rango) | `ERR-002` | Degradable |
| `[not_found]` | No hay datos para ese barrio/categoría | `ERR-003` | Degradable |
| `[source_unavailable]` | Overpass caído y sin datos guardados | `ERR-001` | Degradable |

El mapeo lo hace `error_code()` (definida en `src/tertulia/mcp/client.py`) y `_mcp_event_to_error()` (en `src/tertulia/graph/tool_events.py`).

**Importante:** MCP antepone `"Error executing tool <name>: "` al mensaje, así que el código no está al principio del `event.error`. `error_code()` busca el código en cualquier parte del texto con una regex.

## Errores que no generan evento MCP

CrewAI valida los argumentos de las herramientas contra su esquema **antes** de llamar al MCP. Si los argumentos no son válidos (por ejemplo, `radius_m="lejos"`), lanza `ValueError` y emite `ToolValidateInputErrorEvent`, **no** `MCPToolExecutionFailedEvent`. Por tanto:

- El listener escucha también `ToolValidateInputErrorEvent` y lo mapea a `ERR-002`.
- El agente recibe el error como texto y puede corregirse en el siguiente intento. El sistema lo registra como error recuperable (`retryable=True`).

## Presupuesto de tokens

- Antes de cada llamada al LLM, el nodo comprueba `state["tokens_used"] >= settings.MAX_TOKENS_PER_REPORT`. Si es así, no llama, añade `ERR-006` (fatal) y el grafo termina en `human_approval` sin veredicto.
- Después de cada llamada, el nodo suma los tokens reales (`result.token_usage.total_tokens`, que CrewAI incluye en `CrewOutput`) a `state["tokens_used"]`. Si el crew no los expone para un paso concreto, se estima con `len(prompt)//4 + len(respuesta)//4` y se documenta como estimación.
- El `verdict` que se genere con `ERR-006` es `None` (no hay veredicto). La API debe manejar ese caso y devolver un error claro.

## Lo que queda pendiente (post-demo o Issue #12)

- **`ERR-009` (humano no responde):** implementado en el nodo `human_approval`. El temporizador vive en la API (ver contrato abajo), porque el grafo pausado no tiene reloj interno.
- **`ERR-004` (reintento de LLM):** CrewAI no reintenta por sí solo los fallos del LLM. El reintento con backoff se implementará en el nodo cuando se integre el crew real (Issue #12).
- **`ERR-005` (output inválido):** el adaptador `adapters.py` ya valida con Pydantic. Si se quiere distinguir `ERR-005` de `ERR-002`, se hace en el nodo cuando se integre el crew.

## Contrato de `ERR-009` con la API (timeout humano)

El grafo pausado en `interrupt_before=["human_approval"]` no tiene reloj interno: está esperando. El temporizador vive en la API:

1. La API guarda la hora en que el job se pausó.
2. Si `now - paused_at > settings.HUMAN_TIMEOUT_S` (por defecto 24 h), la API reanuda el grafo con `{"expired": True}` y marca `job["status"] = "expired"`.
3. El nodo `human_approval` lee `expired`, registra `ERR-009` en `errors`, un `TraceEntry` con `tool="ui.timeout"` en `traces`, y termina con `human_approved=False`.
4. La API devuelve `{"ok": false, "reason": "estudio caducado"}` y no genera el PDF.

Valores de `job["status"]` que el frontend debe conocer:

| Estado | Cuándo | Qué muestra el frontend |
|---|---|---|
| `running` | El grafo está ejecutándose o pausado esperando decisión | Barra de progreso / botón de aprobar |
| `done` | Aprobado y PDF generado | Enlace al PDF |
| `rejected` | Rechazado por el humano | «Estudio rechazado» |
| `expired` | Caducado sin respuesta humana (`ERR-009`) | «Estudio caducado» (no es un fallo técnico) |
| `failed` | Error fatal (`ERR-006`, `ERR-008`) | «No se pudo completar el estudio» + detalle del error |

## Tests

| Archivo | Qué cubre |
|---|---|
| `tests/test_tool_events.py` | Mapeo de eventos MCP/validación/uso a `ErrorEntry` (10 tests) |
| `tests/test_errors.py` | Control de tokens (`ERR-006`), excepción interna (`ERR-008`), revisor que falla tratado como rechazo, acumulación de errores (6 tests) |
| `tests/test_graph_flow.py` | Flujo del grafo con HITL: pausa, aprobación, rechazo (3 tests) |
