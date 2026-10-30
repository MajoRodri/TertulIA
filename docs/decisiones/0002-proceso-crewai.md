# 0002 · Proceso de CrewAI dentro de LangGraph

Estado: **decidido** · Issue #23 · Responsable: María Isabel · Revisa: David
Fecha: 30 de octubre de 2026 · Versiones comprobadas: CrewAI 1.15.28, google-genai 1.65

> La checklist pide «justificación del tipo de proceso elegido (secuencial, jerárquico o
> híbrido)». Este documento explica qué elegimos, qué alternativas descartamos y por qué,
> con los datos que medimos o comprobamos en el código. Lo que no está medido se dice.

## 1. Decisión

**Proceso híbrido:** LangGraph decide el flujo y CrewAI ejecuta cada paso en modo
**secuencial**, con una excepción en paralelo.

| Quién | Qué hace |
|---|---|
| **LangGraph** (grafo, David) | Orden de los pasos, bucle de revisión (máximo 3 rondas), pausa para la aprobación humana, errores y trazas. |
| **CrewAI** (crew, María Isabel) | Ejecuta **solo el paso** que le pide cada nodo: `run_step(paso, variables, modelo)`. |

| Nodo del grafo | Paso del crew | Tareas |
|---|---|---|
| research | `research` | `research_task` y `vision_task`, **en paralelo** (son independientes) |
| analyst | `analysis` | `analysis_task` |
| writer | `writing` | `writing_task` |
| reviewer | `review` | `review_task` |

Cada paso crea un `Crew` pequeño con `Process.sequential`. Los resultados de un paso
llegan al siguiente **a través del estado del grafo** (variables `{research_result}`,
`{analysis_result}`, `{draft_report}`…), no a través de la memoria de CrewAI (`context`).

## 2. Alternativas comparadas

| Criterio | A. Secuencial puro (un `kickoff` con las 5 tareas) | B. Jerárquico (un agente «jefe» reparte el trabajo) | **C. Híbrido (elegido)** |
|---|---|---|---|
| Quién decide el orden | CrewAI, siempre el mismo | El modelo que hace de jefe, en cada ejecución | El grafo, con reglas explícitas y testeadas |
| Bucle de revisión (máx. 3) | Repite **las 5 tareas** en cada ronda | Lo decide el jefe: difícil de limitar y de auditar | Repite **solo Redactor y Revisor** |
| Llamadas al modelo | Más llamadas por ronda | Más llamadas: las del jefe se suman a las de los agentes | Las mínimas: cada nodo llama solo a su paso |
| Trazabilidad | Lo intermedio queda dentro de CrewAI | Depende de lo que decida el jefe | Cada resultado pasa por el estado del grafo |
| Aprobación humana y errores | Habría que meterlos en CrewAI | Ídem | Ya los gestiona LangGraph (#13, #14) |
| Encaja con el código del equipo | No: el grafo tiene un nodo por agente | No | **Sí**: acordado con David el 22 de octubre |

**Por qué no el jerárquico:** la rúbrica valora una «autonomía controlada», en la que el
grafo define explícitamente cuándo se avanza, se repite o se para. Un jefe que reparte el
trabajo por su cuenta va en contra de esa idea: es menos predecible, gasta más llamadas y
duplica la orquestación que ya hace LangGraph.

**Por qué no el secuencial puro:** el bucle de revisión obligaría a repetir la
investigación y el análisis en cada ronda, y lo intermedio no quedaría en el estado del grafo.

## 3. Decisiones de diseño dentro del crew

| Decisión | Por qué | Dónde |
|---|---|---|
| `allow_delegation: false` en todos los agentes | Un agente no puede pasar trabajo a otro: solo el grafo orquesta | `agents.yaml` |
| `max_iter` acotado (5; Investigador 12) | CrewAI usa 25 por defecto. Se limita el coste. El Investigador sube a 12 para no cortar una búsqueda a medias (cambio de Majo, 29 oct) | `agents.yaml` |
| Visión: un paso por foto + 2 | Con `max_iter: 5` solo se analizaban 5 de 10 fotos (comprobado con un test) | `crew.py` (`VISION_EXTRA_STEPS`) |
| Herramientas con mínimo privilegio | Cada agente tiene solo las de su trabajo (tabla siguiente) | `agent_tools.py` |
| Resultados por variables, no `context` | Lo intermedio queda en el estado del grafo, que se puede auditar | `tasks.yaml`, `inputs.py` |
| `build_inputs()` rellena siempre todas las variables | CrewAI falla (`KeyError`) si falta una; en la primera ronda van textos por defecto | `inputs.py` |
| Sin fotos, Visión no llama al modelo | Una llamada menos y menos riesgo de error 429 | `crew.py` |
| Si falla Visión, se conserva la investigación | La investigación es imprescindible; la visión no. El usuario ve un mensaje claro y el detalle técnico va al log | `crew.py` |
| Perfiles de sector en YAML | Añadir un sector es añadir un archivo, sin tocar agentes | `config/sectores/` |

**Herramientas por agente**

| Agente | Herramientas | Motivo |
|---|---|---|
| Investigador | `search_competitors`, `search_audience_indicators`, `fetch` (MCP, Helen) | Solo él trae datos de fuera |
| Visión | `analyse_image` (Helen) | Lee las fotos del encargo |
| Analista | `break_even`, `run_python` (Yohanna) | Calcula con código, no de memoria |
| Redactor | Ninguna | Solo usa lo que le pasa el grafo: no puede traer datos sin fuente |
| Revisor | Ninguna | Solo compara el borrador con los resultados |

## 4. Modelo de lenguaje y fiabilidad

El modelo se lee de `config/settings.py` y del `.env`: cambiarlo no exige tocar código.

| Prueba (23 oct, clave gratuita nueva) | Resultado |
|---|---|
| `gemini-3.8-flash` | Sin respuesta: error 504 tras 119 s de espera |
| `gemini-2.5-flash` | Error 404: no disponible para usuarios nuevos |
| `gemini-3.5-flash-lite` | Responde en 1 s → **elegido** |

- **Reintentos y tiempo límite:** con Gemini, CrewAI usa la librería de Google, que sin
  configurar **no reintenta** un error 429 (comprobado con un servidor falso). `build_llm()`
  configura 5 intentos con espera creciente (5, 10, 20 y 40 s) y 90 s por intento.
  `LLM(max_retries=…)` no tiene efecto con Gemini en esta versión de CrewAI.
- **Razonamiento interno desactivado:** CrewAI activa `thinking_config` para Gemini ≥ 2.5 y
  `gemini-3.5-flash-lite` lo rechaza (error 400), así que se desactiva (cambio de Majo, 29 oct).

## 5. Alucinaciones: lo que aprendimos y cómo lo controlamos

En la primera prueba real (23 oct), el Investigador **sin herramientas** inventó cifras
(«7 coworkings», «150–250 €/mes»), fuentes y enlaces genéricos, aunque la tarea le pedía
no hacerlo. **Un prompt no basta.** Por eso hay varias capas:

1. **Aviso explícito:** un agente sin herramientas recibe `NO_TOOLS_NOTE` («no tienes
   herramientas: responde "sin dato"»). Tras el cambio, respondió «sin dato» a todo.
2. **Herramientas reales:** los datos salen de herramientas (MCP, cálculo), no de la memoria.
3. **Fuentes desde los eventos de las herramientas (opción A, #12):** las `Source` y
   `Finding` se construyen con `MCPToolExecutionCompletedEvent`, es decir, con la respuesta
   del servidor, y **nunca** con texto o JSON escrito por el modelo. Descartamos que el crew
   devolviera JSON (opción B), porque el modelo podría inventar enlaces o cifras. Está
   implementado en `adapters.mcp_response_to_sources_and_findings()` y en `main.py`.
4. **Revisor:** comprueba que cada cifra del borrador aparece en la investigación, en el
   análisis o en el chat (marcada como «dato aportado por la persona usuaria»).

## 6. Lo que no delegamos en los agentes

- **Identificadores y confianza:** los asigna el grafo (`compute_confidence()`).
- **Cálculos:** los hacen herramientas deterministas, no el modelo.
- **La decisión final:** la aprueba una persona antes del PDF; si cambia el semáforo,
  queda registrado el motivo.
- **Cambiar las reglas:** el texto del chat y de las webs es información, no instrucciones.

## 7. Privacidad

- `tracing=False` en cada `Crew`: CrewAI no pregunta ni sube prompts y respuestas a sus
  servidores (la primera ejecución lo preguntaba).
- `chat_context` llega ya anonimizado desde la interfaz.
- En la capa gratuita, Google puede usar los datos para mejorar sus productos: solo datos
  de demo; con datos de clientes reales habría que pasar al nivel de pago.

## 8. Limitaciones conocidas

- **Paralelo frente a límites de la API:** Investigador y Visión en paralelo suben las
  peticiones por minuto; los reintentos lo absorben, pero el informe puede tardar más.
- **Tiempos y tokens sin medir:** aún no tenemos el tiempo real de un informe completo ni
  el consumo de tokens (el contador vale 0). Se medirá en la prueba de métricas
  (`docs/metricas.md`).
- **El aviso a los agentes reduce las alucinaciones, pero no las elimina:** la protección
  fuerte son las capas 2 y 3 de la sección 5.

## 9. Cuándo cambiaríamos esta decisión

- Si hiciera falta que los agentes se repartieran trabajo según el caso (por ejemplo,
  muchos sectores con agentes distintos), valoraríamos el proceso jerárquico.
- Si los límites de la API hicieran fallar el paralelo, volveríamos a ejecutar
  Investigación y Visión en serie: es un cambio en `_run_research()`.

## 10. Cómo se comprueba

| Test | Qué garantiza |
|---|---|
| `tests/test_crew_config.py` | Agentes y tareas válidos para CrewAI, sin delegación, sin `context`, sin variables sin definir |
| `tests/test_crew.py` | Cada paso ejecuta sus tareas; paralelo comprobado con una barrera; 10 fotos analizadas; fallo de visión sin perder la investigación; eventos entre hilos llegan a `capture_tool_events()`; reintentos configurados |
| `tests/test_agent_tools.py` | Herramientas por agente y degradación sin MCP |
| `tests/test_sector.py` | Perfiles de sector válidos: campos conocidos, sin repetidos, nombres seguros y de solo lectura |

Todos usan un modelo falso: sin claves, sin internet y sin coste.
