<div align="center">
  <img src="assets/logo.png" alt="TertulIA logo" height="80"/><br/>
  <img src="assets/tertulia.png" alt="TertulIA" height="60"/>
  <h3>Tu guía, tu vía.</h3>
  <p><em>Inteligencia colectiva para negocios locales</em></p>
  <p>Sistema multiagente que analiza la viabilidad de abrir un negocio en un barrio de Madrid: investiga la competencia, analiza la economía y genera un informe en PDF con semáforo de viabilidad.</p>

  <!-- Sustituir # por la URL cuando esté disponible -->
  <a href="#"><img alt="Ver en vivo" src="https://img.shields.io/badge/Ver%20en%20vivo-2B4EFF?style=for-the-badge&logo=googlechrome&logoColor=white"/></a>
  &nbsp;
  <a href="#instalación-y-arranque"><img alt="Ejecutar en local" src="https://img.shields.io/badge/Ejecutar%20en%20local-1a1a2e?style=for-the-badge&logo=python&logoColor=white"/></a>
</div>

---

<!-- Demo en vídeo — sustituir el bloque por el embed cuando esté disponible -->
> 📹 **Vídeo demo** — *próximamente*

---

## ¿Qué es TertulIA?

TertulIA es una herramienta de análisis de viabilidad para negocios locales en Madrid. A partir de información básica sobre tu idea de negocio, un equipo de cinco agentes de inteligencia artificial investiga la competencia real del barrio, analiza los números y genera un informe completo en PDF con un veredicto de viabilidad.

El proceso completo tiene cinco pasos: rellenar el encargo, esperar el debate de los agentes, añadir contexto si lo deseas, revisar el veredicto y aprobar el informe final. La herramienta no garantiza el éxito de ningún negocio.

> El informe es una ayuda para tomar decisiones, no un sustituto del asesoramiento profesional.

---

## El problema

**El 50 % de los negocios locales cierran en los primeros dos años.** La principal causa no es la falta de esfuerzo, sino la falta de información: un estudio de viabilidad profesional cuesta miles de euros y semanas de espera, fuera del alcance de la mayoría de emprendedores.

Los datos existen — en OpenStreetMap, registros del Ayuntamiento de Madrid y portales inmobiliarios — pero están dispersos y requieren horas de cruce manual para convertirse en una decisión útil. **TertulIA automatiza ese proceso de principio a fin en 3-4+ minutos.**

---

## Contenido

- [¿Qué es TertulIA?](#qué-es-tertulia)
- [Arquitectura](#arquitectura)
- [Agentes (CrewAI)](#agentes-crewai)
- [Investigación y datos (MCP)](#investigación-y-datos-mcp)
- [Seguridad](#seguridad)
- [API](#api)
- [Tests](#tests)
- [Añadir un sector](#añadir-un-sector)
- [Instalación y arranque](#instalación-y-arranque)
- [Equipo](#equipo)

---

## Arquitectura

<!-- Diagrama pendiente -->

El flujo principal:

1. La persona rellena un formulario (sector, barrio, presupuesto, fotos opcionales).
2. **5 agentes CrewAI** trabajan en orden orquestados por **LangGraph**: Investigador → Visión → Analista → Redactor → Revisor.
3. La persona revisa el debate, añade contexto por chat y aprueba o rechaza el análisis.
4. Al aprobar se genera un **informe PDF** con semáforo de viabilidad.

---

## Agentes (CrewAI)

El equipo de 5 agentes que hace la investigación. LangGraph decide el orden; CrewAI ejecuta **solo el paso** que le pide cada nodo del grafo. Justificación completa: [`docs/decisiones/0002-proceso-crewai.md`](docs/decisiones/0002-proceso-crewai.md).

<table>
  <tr>
    <td align="center"><img src="assets/portera.png" width="80"/><br/><b>La Portera</b><br/>Investigadora</td>
    <td align="center"><img src="assets/chulapo.png" width="80"/><br/><b>El Chulapo</b><br/>Analista</td>
    <td align="center"><img src="assets/berto.png" width="80"/><br/><b>Berto</b><br/>Especialista Visual</td>
    <td align="center"><img src="assets/pregonero.png" width="80"/><br/><b>El Pregonero</b><br/>Redactor</td>
    <td align="center"><img src="assets/revisora.png" width="80"/><br/><b>La Revisora</b><br/>Revisora</td>
    <td align="center"><img src="assets/berta.png" width="80"/><br/><b>Berta</b><br/>Asistente de chat</td>
  </tr>
  <tr>
    <td align="center"><code>researcher</code></td>
    <td align="center"><code>analyst</code></td>
    <td align="center"><code>vision</code></td>
    <td align="center"><code>writer</code></td>
    <td align="center"><code>reviewer</code></td>
    <td align="center"><code>berta</code></td>
  </tr>
</table>

| Agente | Rol | Herramientas |
| --- | --- | --- |
| La Portera (`researcher`) | Competencia y público del barrio, con fuente | `search_competitors`, `search_audience_indicators`, `fetch` (MCP) |
| Berto (`vision`) | Analiza las fotos aportadas | `analyse_image` |
| El Chulapo (`analyst`) | Punto de equilibrio y gráficos | `break_even`, `run_python` |
| El Pregonero (`writer`) | Informe en Markdown y semáforo propuesto | — |
| La Revisora (`reviewer`) | Comprueba cifras y fuentes del borrador | — |
| Berta | Asistente de chat para aclaraciones | — |

**Cómo llamar al crew:**

```python
from tertulia.crew.crew import llm_from_settings, run_step
from tertulia.crew.inputs import build_inputs
from tertulia.crew.sector import load_sector

llm  = llm_from_settings()
data = build_inputs(brief, load_sector(brief.business_type))
result, tokens = run_step("research", data, llm)
# result → {"research_task": "...", "vision_task": "..."}
```

Pasos: `research` (Investigador y Visión en paralelo), `analysis`, `writing`, `review`. `review_comments()` convierte la respuesta del Revisor en `reviewer_comments` (lista vacía = aprobado).

<details>
<summary>Fiabilidad y configuración del crew</summary>

- Los agentes no pueden delegar trabajo (`allow_delegation: false`) y tienen pasos limitados (`max_iter`).
- Un agente sin herramientas recibe un aviso para responder «sin dato» en vez de inventar (aprendido en la primera prueba real).
- Con Gemini: 5 reintentos ante error 429 y 90 s de tiempo límite por intento.
- `tracing=False`: CrewAI no sube prompts ni respuestas a sus servidores.

**Tests:** `test_sector.py`, `test_crew_config.py`, `test_crew.py` y `test_agent_tools.py`, con un modelo falso: sin claves, sin internet y sin coste.

</details>

---

## Investigación y datos (MCP)

### Servidor MCP `neighbourhood_data`

Nuestro servidor MCP propio. Ofrece a los agentes herramientas de **solo lectura** con datos de barrios de Madrid. Primera fuente: **OpenStreetMap** (vía Overpass API).

| Herramienta | Qué hace | Estado |
| --- | --- | --- |
| `search_competitors(neighbourhood, category="cafe", radius_m=800)` | Busca locales de una categoría (`cafe`, `coworking`) en un radio de 100 a 2.000 m alrededor del centro de un barrio de Madrid. Devuelve nombre, dirección, coordenadas, horario, enlace OSM y fecha de consulta. | ✅ Funciona en directo y en modo demo (Atocha y Delicias) |
| `search_audience_indicators(neighbourhood, radius_m=800)` | Cuenta los lugares de OSM que atraen a cada tipo de público: viajeros, trabajadores, estudiantes, residentes y ocio/restauración. Por grupo: `count` sin duplicados y `highlights` (hasta 5 nombres). | ✅ Funciona en directo y en modo demo |

**Probar a mano:**

```bash
python scripts/try_mcp_server.py
```

<details>
<summary>Decisiones de diseño</summary>

- **Solo lectura (mínimo privilegio):** el servidor no tiene herramientas que envíen, publiquen o borren nada. Si un texto malicioso engaña al modelo, lo peor que puede pasar es una búsqueda de más.
- Todo texto externo pasa por el filtro anti prompt injection antes de devolverse: cada local lleva `suspicious` e `injection_patterns`.
- Transporte **stdio**: el servidor corre en local y las claves de API se leen del `.env`, nunca viajan en los mensajes.
- **El nombre del barrio se valida antes de usarlo en la consulta** (solo letras, espacios y guiones): un nombre con comillas o corchetes podría reescribir la consulta a Overpass (como una inyección SQL).
- **Busca por radio** (800 m por defecto) alrededor del centro del barrio, no dentro de sus límites: en Atocha, OSM tiene 2 cafeterías dentro del barrio y 41 en el radio.

</details>

<details>
<summary>Tolerancia a fallos y modo demo</summary>

- Si el servidor público de Overpass falla, lo reintenta una vez tras 5 s. Las consultas de una llamada comparten un **presupuesto de 110 s** para contestar siempre antes del corte de 150 s del cliente.
- Si falla, cae a los **datos guardados** del barrio (marcados con `from_cache: true` y su fecha de captura); si no los hay, el dato queda como «sin dato». Un fallo nunca se convierte en «0 resultados».
- Con `DEMO_MODE=true` en `.env`, usa siempre los datos guardados de `data/demo_osm/` (Atocha y Delicias): respuesta al instante y sin depender de Overpass. Lo activa una persona antes de arrancar, nunca el modelo.
- **Centro del barrio:** si hay captura guardada, el centro se lee de ella (~35 s menos por llamada).

</details>

<details>
<summary>Códigos de error</summary>

Acordados con el grafo. Cada error del servidor lleva un código:

| Código | Cuándo |
| --- | --- |
| `[invalid_input]` | Barrio, categoría o radio no válidos |
| `[not_found]` | Barrio que no existe en nuestros datos |
| `[source_unavailable]` | OpenStreetMap no responde y no hay datos guardados |

Llegan al grafo a través de los eventos MCP de CrewAI (`MCPToolExecutionFailedEvent`). Se leen con `error_code()` del cliente.

</details>

<details>
<summary>Segunda fuente para coworkings: Foursquare</summary>

OpenStreetMap se queda corto en coworkings. En una prueba el 27 oct, a 800 m de Atocha, OSM tenía 2 y Foursquare 9.

- Para coworkings, en directo, el servidor combina OSM y Foursquare **sin repetir locales** (nombre que coincide y a ≤ 75 m).
- Los locales encontrados **solo en Foursquare** llevan `needs_review: true`: el sistema no descarta nada, **decide el analista** (_human-in-the-loop_).
- La respuesta incluye `confirmed_count`, `needs_review_count`, `foursquare_status` (`used`, `failed`, `no_key` o `not_used`) y `foursquare_limit_reached`.
- Si Foursquare falla o responde algo roto, la búsqueda sigue solo con OSM (`foursquare_status: "failed"`). Las categorías de Foursquare también pasan por el filtro anti prompt injection.
- **Términos de Foursquare:** no permiten guardar sus datos y exigen «Powered by Foursquare». Por eso solo se usa en directo, no en modo demo.
- La clave (`FOURSQUARE_API_KEY`) se lee del `.env` como `SecretStr`. Sin clave, todo funciona solo con OSM.
- ⚠️ `total` incluye los locales por revisar: hasta que el analista los revise, no deben contarse como competidores confirmados.
- **`coverage_note`**: en coworkings sin Foursquare avisa de que puede haber más. Va en la respuesta, no solo en el docstring.

**Tests:** 34 en `tests/test_foursquare.py`, con una copia de una respuesta real.

</details>

<details>
<summary>Indicadores de público (`search_audience_indicators`)</summary>

El informe dejaba «tipo de público» sin dato y en una prueba el agente se lo inventó. Ahora tiene datos reales.

- Una sola consulta a Overpass, generada desde la tabla `AUDIENCE_RULES` (añadir un tipo de lugar = una línea).
- Duplicados: mismo nombre o misma web a ≤ 200 m cuentan una vez.
- Los nombres pasan por el filtro anti prompt injection. `indicator_note`, escrita por el servidor, recuerda que son lugares, no personas contadas.
- Mismo flujo que `search_competitors`: presupuesto de tiempo, caída a datos guardados (`data/demo_osm/audience/`) y modo demo.

**Tests:** 15 en `tests/test_audience_indicators.py`, con lugares reales de Atocha.

</details>

### Cliente MCP (`src/tertulia/mcp/client.py`)

El único sitio donde se dice qué servidores MCP existen, cómo se arrancan y qué herramientas puede usar cada agente. Convierte las herramientas MCP en herramientas de CrewAI con su nombre original:

```python
from tertulia.mcp.client import researcher_tools

Agent(..., tools=researcher_tools())
```

<details>
<summary>Decisiones de diseño del cliente</summary>

- **`tools=` y no `mcps=`:** con la integración nativa de CrewAI, el nombre de la herramienta se recorta a 64 caracteres y el modelo no vería `search_competitors`. `client.py` lee la carta una vez y entrega cada herramienta con su nombre original.
- **Mínimo privilegio:** al servidor solo se le pasa `PYTHONPATH`, nunca nuestras claves de API, y una **lista blanca** decide qué herramientas llegan a cada agente.
- **150 s de espera y una sola llamada:** CrewAI corta por defecto a los 30 s; una búsqueda en directo puede tardar 1-2 minutos.
- **Errores clasificables:** `error_code(event.error)` devuelve el código semántico del servidor (`"invalid_input"`, `"not_found"`, `"source_unavailable"`) o `None` si el error no viene de nuestro servidor.
- Los argumentos mal formados (p. ej. `radius_m="lejos"`) los rechaza CrewAI con su propio esquema antes de llamar a MCP.

</details>

<details>
<summary>Servidor fetch (páginas web de la competencia)</summary>

El servidor oficial `mcp-server-fetch` (Anthropic, MIT) descarga páginas web respetando el `robots.txt`. Sirve para leer las webs de la competencia (carta, precios, horarios).

- **Versión fijada** (`2026.10.24`): la que rechaza direcciones privadas e internas (protección SSRF).
- Esa versión necesita la librería MCP 2.x y CrewAI exige la 1.28, así que se ejecuta con **`uvx`** en su propio entorno aislado. Requiere `uv` (en `requirements.txt`).
- **El texto lo sacamos nosotros** (`src/tertulia/mcp/html_text.py`): su conversor de HTML a texto falla dentro de MCP en Windows, así que pedimos el HTML en bruto (`raw=True`) y lo convertimos con la librería estándar. Funciona igual en Windows, Mac y Linux.
- **Su resultado pasa por nuestro filtro anti prompt injection** en el cliente: el agente lo recibe envuelto en `<external_data>`.

**Tests:** 21 en `tests/test_mcp_client.py`, 7 en `tests/test_html_text.py`, 1 de integración en `tests/test_mcp_integration.py`.

</details>

### Agente de visión (`src/tertulia/vision/`)

Analiza las fotos de locales de la competencia aportadas por la persona usuaria y devuelve observaciones en texto, cada una con la imagen de origen.

- La persona sube las fotos desde la interfaz (jpg/png, máx. 10 MB).
- La herramienta `analyse_image` carga la imagen de forma segura, la reduce a 1.600 px y borra los metadatos GPS.
- **El texto visible dentro de una foto pasa por el filtro anti prompt injection**, igual que el de las webs.
- El modelo nunca describe a las personas: solo indica que aparecen.
- Si el análisis falla (timeout, cuota, respuesta no válida), esa foto falla y las demás continúan.
- El modelo también rellena una **tabla de precios** cuando los ve (Producto / Tamaño / Precio), útil para el ticket medio de la cafetería.
- Modelo: `gemini-3.5-flash-lite` (acepta imágenes). En el nivel gratuito de Google los datos se usan para mejorar sus productos; con fotos de clientes reales habría que usar el nivel de pago.

<details>
<summary>Piezas del agente de visión</summary>

| Pieza | Archivo | Qué hace |
| --- | --- | --- |
| Prueba manual | `scripts/try_vision.py` | Manda una foto al modelo real y muestra lo que ve |
| Formato de respuesta | `vision_schemas.py` | `ImageAnswer`: el formulario que rellena el modelo (tipo, hasta 8 observaciones con categoría y confianza, texto visible, si aparecen personas). `ImageAnalysis`: añade la ruta y la revisión de seguridad |
| Carga segura | `loader.py` | Resuelve la ruta real, exige que esté dentro de `outputs/`, máx. 10 MB, comprueba que es JPEG o PNG de verdad, reduce a 1.600 px y borra metadatos GPS |
| Herramienta | `tool.py` | Une carga, modelo y filtro anti inyección. `to_text()` da el resultado en español para el crew. `AnalyseImageTool` es la herramienta de CrewAI |

Probado con 9 fotos reales, incluyendo una mala hecha a través de una cristalera: el modelo bajó la confianza a «media» sin rechazar la foto.

</details>

**Tests:** 51 (15 del formato, 11 de la carga y 25 de la herramienta), con modelo falso.

**Dependencias:** `mcp~=1.28.1` y `httpx>=0.27`. La versión 2.x de la librería MCP no es compatible con CrewAI: los tutoriales que usen `MCPServer` no sirven tal cual.

---

## Seguridad

Todo texto externo pasa por `process()` antes de llegar a un agente: limpia el HTML, detecta patrones de inyección (español e inglés) y envuelve el contenido en `<external_data id=…>`.

```python
from tertulia.guardrails.injection import process

result = process(text, source="https://example.com")
result.suspicious   # True si se detectó algún patrón
result.patterns     # p. ej. ["ignore_instructions"]
result.wrapped_text # texto limpio y envuelto, listo para el agente
```

El texto sospechoso **no se borra, se marca**: el grafo lo registra en el log y lo muestra como aviso en el veredicto (trazabilidad). Los delimitadores falsos se buscan en el texto original, antes de limpiar.

Defensa en capas: filtro por reglas + herramientas de solo lectura + aprobación humana antes de cualquier acción con impacto.

**Limitaciones conocidas:** es detección por reglas; no detecta frases nuevas ni homoglifos. Por eso es una capa más, no la única.

**Tests:** 38 en `tests/test_injection.py`.

<details>
<summary>Contratos de datos compartidos (`schemas/`)</summary>

Propuestos por Helen como Product Owner y acordados por el equipo el 21 oct. Modelos Pydantic usados por todos los módulos:

| Modelo | Qué representa | Nombre en la interfaz |
| --- | --- | --- |
| `BusinessBrief` | El encargo (sector, barrio, presupuesto, perfil de usuario) | Km. 0 |
| `Source` | De dónde sale un dato (URL, fecha, herramienta, si es sospechoso, si viene de caché) | La Portera |
| `Finding` | Cada dato o cifra del informe, con su fuente o el código que lo calculó | Chulapo Analytics |
| `Verdict` | El semáforo, con confianza, motivos, datos que faltan y corrección del analista | ¿Mola? |
| `TraceEntry` | Una línea del log de auditoría | — |

**Reglas que imponen (Pydantic da error si no se cumplen):**

1. **Toda cifra es trazable:** un `Finding` necesita una fuente o una referencia al código que lo calculó.
2. **Nunca se inventan datos:** si falta un dato, el `Finding` va como `missing` y sin valor.
3. **La decisión final es humana:** el veredicto nace sin aprobar.
4. **Corregir al sistema deja rastro:** el analista puede cambiar el semáforo o la confianza, pero con motivo obligatorio; se guardan las dos versiones.

</details>

<details>
<summary>Gobernanza y roadmap</summary>

Detalle completo: [`docs/etica-y-gobernanza.md`](docs/etica-y-gobernanza.md) · [`docs/fuentes-de-datos.md`](docs/fuentes-de-datos.md)

**Roadmap (datos):** en producción, cargar el extracto de OpenStreetMap de Madrid en una base de datos propia con búsqueda geográfica (PostgreSQL + PostGIS), actualizada cada noche: consultas en milisegundos sin depender del servidor público de Overpass.

**Roadmap (detección):** añadir un clasificador con IA (p. ej. Model Armor de Google Cloud) como segunda capa. No incluido en la entrega porque envía los textos a un tercero y requiere cuenta con facturación.

**Roadmap (reseñas de la competencia):** hoy el informe las deja en «sin dato». Dos vías: campo opcional para pegar reseñas (con el filtro anti inyección) o Google Places API (revisar coste y condiciones de almacenamiento).

</details>

---

## API

| Método | Ruta | Descripción |
| --- | --- | --- |
| `POST` | `/api/analyze` | Inicia un análisis → `{ job_id }` |
| `POST` | `/api/upload/{job_id}` | Sube imágenes → `{ paths }` |
| `GET` | `/api/debate/{job_id}` | SSE con mensajes de los agentes |
| `POST` | `/api/chat/{job_id}` | SSE con respuestas del chat |
| `GET` | `/api/verdict/{job_id}` | Veredicto JSON (incluye `tokens_used`) |
| `POST` | `/api/approve/{job_id}` | Aprueba (devuelve PDF) o rechaza el análisis |

El debate termina con `{ paused: true }` y espera la decisión humana. Al aprobar se genera el PDF con el mismo veredicto que la persona vio en el paso 4.

---

## Tests

```bash
pytest
```

430+ tests. Sin claves, sin internet: usan modelos falsos y datos guardados.

### Métricas de rendimiento

<!-- Pendiente (Yohanna) — resultados comparativos chat normal vs. TertulIA. Ver docs/metricas.md -->

---

## Añadir un sector

1. Copia `config/sectores/_plantilla.yaml` como `config/sectores/<sector>.yaml` (minúsculas y guiones bajos).
2. Rellena qué buscar y qué costes pedir. **Sin cifras:** los importes los aporta la persona usuaria o salen de las fuentes.
3. Ejecuta `pytest`: los tests comprueban que el perfil carga y es válido (campos conocidos, sin repetidos, nombre de archivo igual a `business_type`).

---

## Instalación y arranque

```bash
pip install -e .
cp .env.example .env   # rellena las claves

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

uvicorn src.tertulia.api.main:app --reload --port 8000
```

Abre `http://localhost:8000` en el navegador.

---

## Equipo

| Nombre | GitHub | Papel |
| --- | --- | --- |
| Mariajose Álvarez | [@MajoRodri](https://github.com/MajoRodri) | Scrum Master |
| Elena Díaz | [@HelenDiMo](https://github.com/HelenDiMo) | Product Owner |
| David Rojas | [@drojas-7u7](https://github.com/drojas-7u7) | Developer |
| María Isabel Durango | [@MariaIsaDurango](https://github.com/MariaIsaDurango) | Developer |
| Yohanna Pérez | [@yohperez](https://github.com/yohperez) | Developer |