# TertulIA

---

# README-HELEN · Aportaciones de Helen para el README de TertulIA

> Para Majo: aquí está todo lo de mi parte que debería aparecer en el `README.md` global, en español y en inglés. Coge lo que necesites y adáptalo al formato del README. Lo iré actualizando a medida que termine cada paso.
>

**Última actualización / Last update:** 28 oct 2026

| Módulo / Module | Ruta / Path | Estado / Status |
| --- | --- | --- |
| Filtro anti prompt injection / Prompt injection guard | `src/tertulia/guardrails/injection.py` | ✅ Fusionado / Merged |
| Contratos de datos (propuesta como PO) / Data contracts (proposed as PO) | `src/tertulia/schemas/` | ✅ Fusionado / Merged |
| Servidor MCP / MCP server `neighbourhood_data` | `src/tertulia/mcp/servers/neighbourhood_data/` | ✅ Fusionado / Merged (PR #49) |
| Foursquare como segunda fuente / Foursquare as second source | `src/tertulia/mcp/servers/neighbourhood_data/server.py` | ✅ Fusionado / Merged (PR #64) |
| `BusinessBrief.image_paths` | `src/tertulia/schemas/models.py` | ✅ Fusionado / Merged (PR #60) |
| Cliente MCP y servidor fetch / MCP client and fetch server | `src/tertulia/mcp/client.py`, `src/tertulia/mcp/html_text.py` | ✅ Fusionado / Merged (PR #58) |
| Agente de visión / Vision agent | `src/tertulia/vision/` | ✅ Fusionado / Merged (PR #66, #67) |

---

# 🇪🇸 Español

## 1. Filtro anti prompt injection

**Qué hace.** Todo texto que llega de fuera (webs, reseñas, descripciones de locales) pasa por `process()` antes de llegar a un agente. El filtro:

1. **Limpia** el texto: quita scripts, etiquetas HTML y caracteres invisibles, traduce las entidades HTML, junta los espacios y recorta a 8.000 caracteres.
2. **Detecta** frases típicas de inyección en español e inglés (ignorar instrucciones, cambiar de rol, pedir el prompt del sistema, ordenar acciones, delimitadores falsos), sobre una copia normalizada (minúsculas, sin tildes ni letras disfrazadas).
3. **Envuelve** el texto en `<external_data id=…>` con un id aleatorio y un aviso de que son datos, no instrucciones. Escapa `<` y `>` para que nada de dentro parezca una etiqueta.

**Uso:**

```python
from tertulia.guardrails.injection import process

result = process(text, source="https://example.com")
result.suspicious      # True si se detectó algún patrón
result.patterns        # p. ej. ["ignore_instructions"]
result.wrapped_text    # texto limpio y envuelto, para el agente
```

**Decisiones de diseño:**

- El texto sospechoso **no se borra, se marca**: el grafo no lo usa para ningún hallazgo, lo registra en el log y lo muestra como aviso en el veredicto (trazabilidad).
- Los delimitadores falsos se buscan en el texto original, antes de limpiarlo, para que el intento quede registrado.
- **Limitaciones conocidas:** es una detección por reglas; no detecta frases nuevas que no estén en la lista ni letras de otros alfabetos que imitan a las latinas (homoglifos). Por eso es **una capa más**, no la única: la otra defensa es que ninguna acción con impacto se ejecute sin aprobación humana.

**Tests:** 30 en `tests/test_injection.py`.

## 2. Contratos de datos compartidos (`schemas/`)

Propuestos por Helen como Product Owner y acordados por el equipo el 21 oct. Modelos Pydantic que usan todos los módulos:

| Modelo | Qué representa | Nombre en la interfaz |
| --- | --- | --- |
| `BusinessBrief` | El encargo (sector, barrio, presupuesto, perfil de usuario) | Km. 0 |
| `Source` | De dónde sale un dato (URL, fecha, herramienta, si es sospechoso, si viene de caché) | La Portera |
| `Finding` | Cada dato o cifra del informe, con su fuente o el código que lo calculó | Chulapo Analytics |
| `Verdict` | El semáforo, con confianza, motivos, datos que faltan, avisos y corrección del analista | ¿Mola? |
| `TraceEntry` | Una línea del log de auditoría | — |

**Reglas que imponen (Pydantic da error si no se cumplen):**

1. **Toda cifra es trazable:** un `Finding` necesita una fuente o una referencia al código que lo calculó.
2. **Nunca se inventan datos:** si falta un dato, el `Finding` va como `missing` y sin valor.
3. **La decisión final es humana:** el veredicto nace sin aprobar.
4. **Corregir al sistema deja rastro:** el analista puede cambiar el semáforo o la confianza, pero con motivo obligatorio; se guardan las dos versiones.

La confianza la calcula el grafo con una fórmula fija (`compute_confidence()`), cuyos pesos se ajustan en `config/settings.py`.

## 3. Servidor MCP `neighbourhood_data`

**Qué es.** Nuestro servidor MCP propio. Ofrece a los agentes herramientas de **solo lectura** con datos de barrios de Madrid. Primera fuente: **OpenStreetMap** (vía Overpass API).

**Herramientas:**

| Herramienta | Qué hace | Estado |
| --- | --- | --- |
| `search_competitors(neighbourhood, category="cafe", radius_m=800)` | Busca locales de una categoría (`cafe`, `coworking`) en un radio de 100 a 2.000 m alrededor del centro de un barrio o distrito de Madrid. Devuelve nombre, marca, dirección, coordenadas, horario, fecha de comprobación y enlace a OSM de cada local, más el total, la atribución y la fecha de consulta | ✅ Funciona con OpenStreetMap en directo (22 cafeterías en 800 m alrededor de Atocha, 22 oct). ✅ Reserva con datos guardados y modo demo (Atocha y Delicias) |

**Probarlo a mano:**

```bash
python scripts/try_mcp_server.py
```

El script arranca el servidor, pide su lista de herramientas (`tools/list`), llama a `search_competitors` (`tools/call`) y muestra cómo se rechaza una llamada mal formada.

**Decisiones de diseño:**

- **Solo lectura (mínimo privilegio):** el servidor no tiene herramientas que envíen, publiquen o borren nada. Si un texto malicioso engaña al modelo, lo peor que puede pasar es una búsqueda de más (evita la *excessive agency*).
- Todo texto externo pasa por el filtro anti prompt injection antes de devolverse: cada local lleva `suspicious` e `injection_patterns` (los mismos campos que el schema `Source`). Los locales sospechosos se marcan, no se borran.
- Transporte **stdio**: el servidor corre en local y las claves de API se leen del `.env`, nunca viajan en los mensajes.
- **El nombre del barrio se valida antes de usarlo en la consulta** (solo letras, espacios y guiones): lo escribe el modelo, y un nombre con comillas o corchetes podría reescribir la consulta a Overpass (como una inyección SQL).
- **Busca por radio** (800 m por defecto) alrededor del centro del barrio, no dentro de sus límites: en Atocha, OpenStreetMap tiene 2 cafeterías dentro del barrio y 41 en el radio.
- **Tolerancia a fallos:** si el servidor público de Overpass falla (por ejemplo, un 502 puntual), lo reintenta una vez tras 10 s y deja un aviso en el log. Si vuelve a fallar, usa los **datos guardados** del barrio (marcados con `from_cache=True` y su fecha de captura); si no los hay, el dato queda como «sin dato». Un fallo nunca se convierte en «0 resultados».
- **Modo demo:** con `DEMO_MODE=true` en el `.env`, la herramienta usa siempre los datos guardados de `data/demo_osm/` (Atocha y Delicias, capturados con 2.000 m y filtrados por distancia al radio pedido): respuesta al instante y sin depender de Overpass. Lo activa una persona antes de arrancar, nunca el modelo; cada resultado sigue indicando `from_cache: true` y la fecha de captura.

**Códigos de error** (acordados con el grafo): cada error del servidor lleva un código, `[invalid_input]` (barrio, categoría o radio no válidos), `[not_found]` (barrio que no existe) o `[source_unavailable]` (OpenStreetMap no responde y no hay datos guardados). Llegan al grafo a través de los eventos MCP de CrewAI (`MCPToolExecutionFailedEvent`). MCP antepone «Error executing tool search_competitors: », así que el código no va al principio: se lee con `error_code()` del cliente (sección 4).

**Dependencias:** `mcp~=1.28.1` y `httpx>=0.27` en `requirements.txt`. `mcp~=1.28.1` es la versión que exige CrewAI. La versión 2.x de la librería cambia la API (`FastMCP` pasa a llamarse `MCPServer`) y no es compatible con CrewAI: los tutoriales que usen `MCPServer` no sirven tal cual.

**Fuente de datos:** © OpenStreetMap contributors, licencia ODbL (permite guardar los datos para la demo sin internet, citando la fuente).

**Segunda fuente para coworkings: Foursquare (solo en directo).** OpenStreetMap se queda corto en coworkings: en una prueba el 27 oct, a 800 m de Atocha, OSM tenía 2 y Foursquare 9, pero varios de Foursquare eran sedes de empresas, porque allí las categorías las ponen sus usuarios.

- Para coworkings, en directo, el servidor combina OSM y Foursquare **sin repetir locales** (nombre que coincide y a ≤ 75 m).
- Lo que aparece **solo en Foursquare** lleva `needs_review: true` y un `review_reason`: el sistema no descarta nada, **decide el analista** (*human-in-the-loop*).
- Cada local indica sus fuentes (`sources`). La respuesta incluye `needs_review_count` y `foursquare_status` (`used`, `failed` o `not_used`).
- **Términos de Foursquare:** no permiten guardar sus datos (solo el identificador) y exigen «Powered by Foursquare». Por eso solo se usa en directo, no se guarda nada y en modo demo, con datos guardados o si falla, se usa solo OSM.
- La clave (`FOURSQUARE_API_KEY`) la lee el propio servidor del `.env`, como `SecretStr` (nunca sale en logs). Sin clave, todo funciona solo con OSM.
- ⚠️ `total` incluye los locales por revisar: hasta que el analista revise, no deben contarse como competidores confirmados.
- **Tests:** 14 en `tests/test_foursquare.py`, con una copia de una respuesta real (sin llamadas a la API).

## 4. Cliente MCP (`src/tertulia/mcp/client.py`)

**Qué es.** El único sitio donde se dice qué servidores MCP existen, cómo se arrancan y qué herramientas puede usar cada agente. Convierte las herramientas MCP en herramientas de CrewAI listas para usar:

```python
from tertulia.mcp.client import researcher_tools

Agent(..., tools=researcher_tools())
```

**Decisiones de diseño:**

- **`tools=` y no `mcps=`:** con la integración nativa de CrewAI (`mcps=`), el nombre de la herramienta se forma con la ruta del servidor y se recorta a 64 caracteres (el modelo no vería `search_competitors`), y las herramientas se añaden al ejecutar la tarea, no al crear el agente. `client.py` lee la carta una vez y entrega cada herramienta con su nombre original.
- **Mínimo privilegio:** al servidor solo se le pasa `PYTHONPATH`, nunca nuestras claves de API, y una **lista blanca** decide qué herramientas llegan a cada agente.
- **150 s de espera y una sola llamada:** CrewAI corta por defecto a los 30 s y repite hasta 3 veces; una búsqueda en directo en OpenStreetMap tarda 1–2 minutos y el servidor ya reintenta y usa sus datos guardados.
- **Errores clasificables:** el grafo escucha los eventos MCP de CrewAI (`MCPToolExecutionCompletedEvent` y `MCPToolExecutionFailedEvent`) y saca el código con `error_code(event.error)`, que devuelve el código semántico del servidor (`"invalid_input"`, `"not_found"`, `"source_unavailable"`) o `None` si el error no viene de nuestro servidor (timeout, conexión, fetch). No son los códigos ERR-XXX del grafo: el grafo los traduce a los suyos.
- **Ojo:** los argumentos mal formados (p. ej. `radius_m="lejos"`) los rechaza CrewAI con su propio esquema antes de llamar a MCP, así que no generan `MCPToolExecutionFailedEvent`. El agente recibe el error como texto y puede corregirse.

**Servidor existente: fetch.** El servidor oficial `mcp-server-fetch` (Anthropic, MIT) descarga páginas web respetando el `robots.txt`. Sirve para leer las webs de la competencia (carta, precios, horarios).

- **Versión fijada** (`2026.10.24`): la que rechaza direcciones privadas e internas (protección SSRF).
- Esa versión necesita la librería MCP 2.x y CrewAI exige la 1.28, así que se ejecuta con **`uvx`** en su propio entorno aislado. Requiere `uv` (en `requirements.txt`).
- **El texto lo sacamos nosotros** (`src/tertulia/mcp/html_text.py`): su conversor de HTML a texto (readabilipy) falla dentro de MCP en Windows, así que le pedimos el HTML en bruto (`raw=True`) y lo convertimos con la librería estándar de Python (`html.parser`). Funciona igual en Windows, Mac y Linux, sin dependencias nuevas. El agente solo puede pedir `url` y `max_length` (100–20.000 caracteres).
- **Su resultado pasa por nuestro filtro anti prompt injection** en el cliente: el agente lo recibe envuelto en `<external_data>` y marcado si parece sospechoso. Nuestro servidor ya filtra por dentro; uno de terceros, no.

**Tests:** 21 en `tests/test_mcp_client.py`, sin arrancar ningún servidor; 7 del conversor en `tests/test_html_text.py`, y 1 de integración en `tests/test_mcp_integration.py`, que arranca el servidor real y comprueba el error tal como le llega al grafo (sin internet).

## 5. Agente de visión (`src/tertulia/vision/`) (#32)

**Qué hará.** Analizar las fotos de locales de la competencia y los gráficos del análisis, y devolver una lista de observaciones en texto, cada una con la imagen de la que sale.

**Decidido hasta ahora (27 oct):**

- **De dónde salen las fotos:** las sube la consultora desde la interfaz (pueden ser fotos que haga ella en el barrio). Solo imágenes (jpg/png); los PDF quedan para más adelante.
- **Cómo viajan:** dentro de la petición, en un campo nuevo `BusinessBrief.image_paths` (opcional), así que no cambia el contrato del grafo.
- **Uso de las fotos:** en el producto, solo interno: el analista abre cada foto para comprobar lo que dice el informe. En la demo de clase sí se muestran, con su fuente citada.
- **Herramienta propia `analyse_image`** en vez de la opción multimodal de CrewAI: así controlamos qué archivos se aceptan y el formato de la respuesta, y **el texto que aparezca dentro de una foto pasa por el filtro anti prompt injection**, igual que el de las webs.
- **Modelo:** `gemini-3.5-flash-lite` (acepta imágenes). En el nivel gratuito de Google los datos se usan para mejorar sus productos, así que con fotos de clientes reales habría que usar el nivel de pago.

**Hecho (27-28 oct, PR #66 y #67):**

| Pieza | Archivo | Qué hace |
| --- | --- | --- |
| Prueba manual | `scripts/try_vision.py` | Manda una foto al modelo real (una llamada) y muestra lo que ve |
| Formato de respuesta | `vision_schemas.py` | `ImageAnswer`: el formulario que rellena el modelo (tipo, hasta 8 observaciones con categoría y confianza alta/media/baja, texto visible, si aparecen personas, motivo si no se puede analizar). `ImageAnalysis`: añade lo que pone nuestro código (la ruta y la revisión de seguridad), que el modelo no puede elegir |
| Carga segura | `loader.py` | Resuelve la ruta real (enlaces incluidos) y exige que esté dentro de `outputs/`; máximo 10 MB; comprueba que el contenido es JPEG o PNG de verdad; la reduce a 1.600 px y la guarda sin metadatos (se borra la posición GPS) |
| Herramienta | `tool.py` | `analyse_image()` une todo: carga, modelo con formulario fijo y **filtro anti prompt injection sobre el texto visible y las observaciones**. `to_text()` lo da en español para el crew. `AnalyseImageTool` es la herramienta de CrewAI para el agente `vision` (texto envuelto en `<external_data>`) |

Probado en directo con Gemini: leyó la pizarra de un bar (la oferta del competidor) y no inventó precios que no se veían. **Nunca describe a las personas**: solo indica que aparecen. Si la respuesta del modelo no encaja con el formulario, **o el modelo no contesta** (timeout, conexión, cuota), se lanza `AnalysisFailed`: esa foto falla, las demás siguen y la herramienta lo explica en texto, sin usar nunca un análisis a medias.

**Probado con 9 fotos reales** (bar, cafetería y coworkings), incluida una mala hecha a través de una cristalera: el modelo bajó la confianza a «media» sin rechazar la foto. El prompt explica qué significa cada categoría (por ejemplo, «espacio de trabajo» es para los clientes; la barra de un café no cuenta), cuándo bajar la confianza y que la calidad de la foto no es una observación. `vision/` no importa nada de `crew/`: la herramienta recibe siempre el modelo, así que las dependencias van en una sola dirección.

**Tests:** 39 (9 del formato, 11 de la carga y 19 de la herramienta), con un modelo falso y sin gastar llamadas.

## 6. Seguridad y gobernanza (aportaciones)

- Defensa en capas contra prompt injection: filtro por reglas + envoltorio de datos + herramientas de solo lectura + aprobación humana antes de cualquier acción con impacto.
- **Roadmap (datos):** en producción, cargar el extracto de OpenStreetMap de Madrid en una base de datos propia con búsqueda geográfica (por ejemplo, PostgreSQL + PostGIS), actualizada cada noche: consultas en milisegundos y sin depender del servidor público de Overpass. Opcionalmente, un servidor MCP siempre encendido por HTTP y los informes como tareas en segundo plano.
- **Roadmap:** añadir un clasificador con IA (por ejemplo, Model Armor de Google Cloud) como segunda capa de detección. No se incluye en la entrega porque envía los textos a un tercero y requiere una cuenta con facturación.

---

# 🇬🇧 English

## 1. Prompt injection guard

**What it does.** Every external text (web pages, reviews, venue descriptions) goes through `process()` before it reaches an agent. The guard:

1. **Cleans** the text: strips scripts, HTML tags and invisible characters, decodes HTML entities, collapses whitespace and truncates to 8,000 characters.
2. **Detects** typical injection phrases in Spanish and English (ignore instructions, role change, system prompt leak, action commands, fake delimiters) on a normalised copy (lowercase, no accents, no look-alike characters).
3. **Wraps** the text in `<external_data id=…>` with a random id and a note saying it is data, not instructions. It escapes `<` and `>` so nothing inside can look like a tag.

**Usage:**

```python
from tertulia.guardrails.injection import process

result = process(text, source="https://example.com")
result.suspicious      # True if any pattern was found
result.patterns        # e.g. ["ignore_instructions"]
result.wrapped_text    # cleaned and wrapped text, for the agent
```

**Design decisions:**

- Suspicious text is **flagged, not deleted**: the graph does not use it for any finding, records it in the log and shows it as a warning in the verdict (traceability).
- Fake delimiters are searched in the original text, before cleaning, so the attempt is logged.
- **Known limitations:** it is rule-based detection; it misses new phrases that are not in the list and letters from other alphabets that imitate Latin ones (homoglyphs). That is why it is **one layer**, not the only one: the other defence is that no high-impact action runs without human approval.

**Tests:** 30 in `tests/test_injection.py`.

## 2. Shared data contracts (`schemas/`)

Proposed by Helen as Product Owner and agreed by the team on 21 Oct. Pydantic models used by every module:

| Model | What it represents | UI name |
| --- | --- | --- |
| `BusinessBrief` | The request (sector, neighbourhood, budget, user profile) | Km. 0 |
| `Source` | Where a piece of data comes from (URL, date, tool, suspicious flag, cache flag) | La Portera |
| `Finding` | Each fact or figure in the report, with its source or the code that computed it | Chulapo Analytics |
| `Verdict` | The traffic light, with confidence, reasons, missing data, warnings and analyst override | ¿Mola? |
| `TraceEntry` | One line of the audit log | — |

**Rules they enforce (Pydantic raises an error otherwise):**

1. **Every figure is traceable:** a `Finding` needs a source or a reference to the code that computed it.
2. **Data is never invented:** if a value is missing, the `Finding` is `missing` and has no value.
3. **The final decision is human:** the verdict starts unapproved.
4. **Overriding the system leaves a trace:** the analyst can change the traffic light or the confidence, but must give a reason; both versions are kept.

Confidence is computed by the graph with a fixed formula (`compute_confidence()`), whose weights are set in `config/settings.py`.

## 3. MCP server `neighbourhood_data`

**What it is.** Our own MCP server. It gives the agents **read-only** tools with data about Madrid neighbourhoods. First source: **OpenStreetMap** (via the Overpass API).

**Tools:**

| Tool | What it does | Status |
| --- | --- | --- |
| `search_competitors(neighbourhood, category="cafe", radius_m=800)` | Finds venues of a category (`cafe`, `coworking`) within 100 to 2,000 m of the centre of a Madrid barrio or district. Returns each venue's name, brand, address, coordinates, opening hours, check date and OSM link, plus the total, the attribution and the retrieval date | ✅ Works with live OpenStreetMap data (22 cafés within 800 m of Atocha, 22 Oct). ✅ Saved-data fallback and demo mode (Atocha and Delicias) |

**Try it by hand:**

```bash
python scripts/try_mcp_server.py
```

The script starts the server, asks for its tool list (`tools/list`), calls `search_competitors` (`tools/call`) and shows how a malformed call is rejected.

**Design decisions:**

- **Read-only (least privilege):** the server has no tools that send, publish or delete anything. If malicious text tricks the model, the worst outcome is an extra search (it avoids *excessive agency*).
- All external text goes through the prompt injection guard before being returned: each venue carries `suspicious` and `injection_patterns` (the same fields as the `Source` schema). Suspicious venues are flagged, not deleted.
- **stdio** transport: the server runs locally and API keys are read from `.env`; they never travel in the messages.
- **The neighbourhood name is validated before it goes into the query** (letters, spaces and hyphens only): the model writes it, and a name with quotes or brackets could rewrite the Overpass query (like an SQL injection).
- **Radius search** (800 m by default) around the neighbourhood centre, not inside its boundary: in Atocha, OpenStreetMap has 2 cafés inside the barrio and 41 within the radius.
- **Fault tolerance:** if the public Overpass server fails (for example, a one-off 502), it retries once after 10 s and logs a warning. If it fails again, it uses the neighbourhood's **saved data** (marked `from_cache=True`, with its capture date); if there is none, the value is reported as missing. A failure never becomes "0 results".
- **Demo mode:** with `DEMO_MODE=true` in `.env`, the tool always uses the saved data in `data/demo_osm/` (Atocha and Delicias, captured within 2,000 m and filtered by distance to the requested radius): instant answers that do not depend on Overpass. A person turns it on before starting, never the model; every result still says `from_cache: true` and gives the capture date.

**Error codes** (agreed with the graph): every server error carries a code, `[invalid_input]` (invalid neighbourhood, category or radius), `[not_found]` (neighbourhood does not exist) or `[source_unavailable]` (OpenStreetMap does not respond and there is no saved data). They reach the graph through CrewAI's MCP events (`MCPToolExecutionFailedEvent`). MCP puts "Error executing tool search_competitors: " in front, so the code is not at the start: it is read with the client's `error_code()` (section 4).

**Dependencies:** `mcp~=1.28.1` and `httpx>=0.27` in `requirements.txt`. `mcp~=1.28.1` is the version CrewAI requires. Version 2.x of the library changes the API (`FastMCP` becomes `MCPServer`) and is not compatible with CrewAI: tutorials using `MCPServer` will not work as they are.

**Data source:** © OpenStreetMap contributors, ODbL licence (it allows storing the data for the offline demo, as long as the source is credited).

**Second source for coworkings: Foursquare (live only).** OpenStreetMap falls short on coworkings: in a test on 27 Oct, within 800 m of Atocha, OSM had 2 and Foursquare 9, but several of the Foursquare ones were company offices, because its categories are set by its users.

- For coworkings, live, the server combines OSM and Foursquare **without repeating venues** (matching name, at most 75 m apart).
- Venues found **only in Foursquare** get `needs_review: true` and a `review_reason`: the system discards nothing, **the analyst decides** (*human-in-the-loop*).
- Each venue lists its sources (`sources`). The answer includes `needs_review_count` and `foursquare_status` (`used`, `failed` or `not_used`).
- **Foursquare's terms:** its data cannot be stored (only the id) and "Powered by Foursquare" is required. So it is used live only, nothing is stored, and in demo mode, with saved data or if it fails, OpenStreetMap alone is used.
- The key (`FOURSQUARE_API_KEY`) is read by the server itself from `.env`, as a `SecretStr` (never shown in logs). Without a key, everything works with OSM alone.
- ⚠️ `total` includes venues pending review: until the analyst reviews them, they must not count as confirmed competitors.
- **Tests:** 14 in `tests/test_foursquare.py`, with a copy of a real answer (no API calls).

## 4. MCP client (`src/tertulia/mcp/client.py`)

**What it is.** The only place that says which MCP servers exist, how to start them and which tools each agent may use. It turns MCP tools into ready-to-use CrewAI tools:

```python
from tertulia.mcp.client import researcher_tools

Agent(..., tools=researcher_tools())
```

**Design decisions:**

- **`tools=`, not `mcps=`:** with CrewAI's native integration (`mcps=`), the tool name is built from the server path and cut to 64 characters (the model would not see `search_competitors`), and tools are added when the task runs, not when the agent is created. `client.py` reads the tool list once and returns each tool with its original name.
- **Least privilege:** the server only gets `PYTHONPATH`, never our API keys, and an **allow list** decides which tools reach each agent.
- **150 s timeout and a single call:** by default CrewAI stops after 30 s and repeats up to 3 times; a live OpenStreetMap search takes 1–2 minutes and the server already retries and falls back to its saved data.
- **Classifiable errors:** the graph listens to CrewAI's MCP events (`MCPToolExecutionCompletedEvent` and `MCPToolExecutionFailedEvent`) and gets the code with `error_code(event.error)`, which returns the server's semantic code (`"invalid_input"`, `"not_found"`, `"source_unavailable"`) or `None` when the error does not come from our server (timeout, connection, fetch). These are not the graph's ERR-XXX codes: the graph maps them to its own.
- **Note:** malformed arguments (e.g. `radius_m="lejos"`) are rejected by CrewAI's own schema before MCP is called, so they produce no `MCPToolExecutionFailedEvent`. The agent gets the error as text and can correct itself.

**Existing server: fetch.** The official `mcp-server-fetch` server (Anthropic, MIT) downloads web pages, respecting `robots.txt`. It is used to read competitors' websites (menus, prices, opening hours).

- **Pinned version** (`2026.10.24`): the one that refuses private and internal addresses (SSRF protection).
- That version needs the MCP library 2.x while CrewAI requires 1.28, so it runs with **`uvx`** in its own isolated environment. It requires `uv` (in `requirements.txt`).
- **We extract the text ourselves** (`src/tertulia/mcp/html_text.py`): its HTML-to-text converter (readabilipy) breaks inside MCP on Windows, so we ask for the raw HTML (`raw=True`) and convert it with Python's standard library (`html.parser`). It works the same on Windows, Mac and Linux, with no new dependency. The agent can only ask for `url` and `max_length` (100–20,000 characters).
- **Its output goes through our prompt injection guard** in the client: the agent receives it wrapped in `<external_data>` and flagged if it looks suspicious. Our own server already filters inside; a third-party one does not.

**Tests:** 21 in `tests/test_mcp_client.py`, without starting any server; 7 for the converter in `tests/test_html_text.py`; and 1 integration test in `tests/test_mcp_integration.py`, which starts the real server and checks the error exactly as the graph receives it (no internet needed).

## 5. Vision agent (`src/tertulia/vision/`) (#32)

**What it will do.** Analyse photos of competitors' venues and the analysis charts, and return a list of text observations, each with the image it comes from.

**Decided so far (27 Oct):**

- **Where the photos come from:** the consultancy uploads them from the UI (they can take them in the neighbourhood). Images only (jpg/png); PDFs are left for later.
- **How they travel:** inside the request, in a new optional field `BusinessBrief.image_paths`, so the graph contract does not change.
- **Use of the photos:** in the product, internal only: the analyst opens each photo to check what the report says. In the class demo they are shown, with their source credited.
- **Our own `analyse_image` tool** instead of CrewAI's multimodal option: we control which files are accepted and the answer format, and **any text that appears inside a photo goes through the prompt injection guard**, like web text.
- **Model:** `gemini-3.5-flash-lite` (accepts images). On Google's free tier the data is used to improve their products, so with real client photos the paid tier would be needed.

**Done (27-28 Oct, PR #66 and #67):**

| Piece | File | What it does |
| --- | --- | --- |
| Manual test | `scripts/try_vision.py` | Sends one photo to the real model (one call) and prints what it sees |
| Answer format | `vision_schemas.py` | `ImageAnswer`: the form the model fills in (kind, up to 8 observations with category and high/medium/low confidence, visible text, whether people appear, reason if it cannot be analysed). `ImageAnalysis`: adds what our code sets (the path and the safety check), which the model cannot choose |
| Safe loading | `loader.py` | Resolves the real path (links included) and requires it to be inside `outputs/`; 10 MB max; checks the content really is JPEG or PNG; reduces it to 1,600 px and saves it without metadata (the GPS position is removed) |
| Tool | `tool.py` | `analyse_image()` joins it all: loading, the model with a fixed form and **the prompt injection guard on the visible text and the observations**. `to_text()` gives it in Spanish for the crew. `AnalyseImageTool` is the CrewAI tool for the `vision` agent (text wrapped in `<external_data>`) |

Tested live with Gemini: it read a bar's chalkboard (the competitor's offer) and did not invent prices that could not be seen. **It never describes people**: it only says they appear. If the model's answer does not fit the form, **or the model does not answer** (timeout, connection, quota), `AnalysisFailed` is raised: that photo fails, the others carry on, and the tool explains it as text, never using a half-filled analysis.

**Tested with 9 real photos** (bar, café and coworkings), including a poor one taken through a window: the model lowered its confidence to "medium" without rejecting the photo. The prompt explains what each category means (e.g. "workspace" is for customers; a coffee bar counter does not count), when to lower the confidence, and that the photo's quality is not an observation. `vision/` imports nothing from `crew/`: the tool always receives the model, so dependencies go one way only.

**Tests:** 39 (9 for the format, 11 for loading and 19 for the tool), with a fake model and no API calls.

## 6. Security and governance (contributions)

- Defence in layers against prompt injection: rule-based guard + data wrapping + read-only tools + human approval before any high-impact action.
- **Roadmap (data):** in production, load the Madrid OpenStreetMap extract into our own database with geographic search (for example, PostgreSQL + PostGIS), refreshed every night: millisecond queries without depending on the public Overpass server. Optionally, an always-on MCP server over HTTP and reports as background jobs.
- **Roadmap:** add an AI-based classifier (for example, Google Cloud Model Armor) as a second detection layer. Not included in this delivery because it sends the texts to a third party and needs a billing account.