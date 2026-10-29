# Fuentes de datos de TertulIA

Issue #34 · Responsable: Helen · Última revisión: 29 oct 2026

Qué dato da cada fuente, cómo lo usamos, qué dicen sus términos de uso y cuáles son sus límites. Regla de todo el proyecto: **cada cifra del informe lleva su fuente y su fecha; si un dato no está, se escribe «sin dato» y nunca se inventa**.

## Resumen

| Fuente | Qué da | Cómo entra | ¿Se guarda? | Atribución obligatoria |
| --- | --- | --- | --- | --- |
| OpenStreetMap (Overpass API) | Cafeterías, coworkings e indicadores de público en un radio | Servidor MCP `neighbourhood_data` | Sí (ODbL), en `data/demo_osm/` | «© OpenStreetMap contributors» |
| Foursquare Places API | Coworkings que no están en OSM | Servidor MCP `neighbourhood_data`, solo en directo | **No** (solo el id) | «Powered by Foursquare» |
| Webs públicas (servidor MCP `fetch`) | Texto de webs de la competencia (cartas, tarifas) | Herramienta `fetch` del Researcher | No | Se cita la URL |
| Fotos que sube la persona usuaria | Ambiente, oferta, capacidad y precios de cartas | Agente de visión (`analyse_image`) | Solo durante el análisis, en `outputs/` | Se cita el archivo |
| Datos que escribe la persona usuaria | Presupuesto, superficie, notas de contexto | Formulario y chat | No (memoria de la sesión) | Fuente `user_input` |
| Modelo de lenguaje (Gemini) | Razonamiento y redacción, **no datos** | CrewAI | — | — |

## 1. OpenStreetMap (vía Overpass API)

**Qué es.** Mapa colaborativo hecho por voluntarios. Lo consultamos con la API pública de Overpass (`overpass-api.de`).

**Qué usamos:**

- `search_competitors(neighbourhood, category, radius_m)`: cafeterías (`amenity=cafe`) y coworkings (`amenity=coworking_space` u `office=coworking`) a 100–2.000 m del centro de un barrio o distrito de Madrid (800 m por defecto).
- `search_audience_indicators(neighbourhood, radius_m)`: lugares que atraen a cada tipo de público. Son **indicadores, no personas contadas**:

| Grupo | Qué se cuenta |
| --- | --- |
| Viajeros | Estaciones, hoteles, hostales, apartamentos turísticos y museos |
| Trabajadores | Oficinas (sin coworkings) y polígonos industriales |
| Estudiantes | Universidades, centros de FP y bibliotecas |
| Vecinos | Supermercados, colegios, centros de salud y farmacias |
| Comida y ocio | Restaurantes, bares, comida rápida, cines y teatros |

**Términos de uso:**

- Licencia **ODbL** (Open Database License). Permite usar, guardar y compartir los datos **citando la fuente**: cada respuesta del servidor lleva el campo `attribution` con «© OpenStreetMap contributors (ODbL)».
- Si publicáramos una base de datos derivada, tendría que compartirse con la misma licencia (*share-alike*). Nuestras capturas solo se usan para la demo.
- El servidor público de Overpass pide un uso moderado y que cada cliente se identifique: enviamos un `User-Agent` propio (`TertulIA/0.1 …`).

**Límites que hemos visto:**

- **Lo mapean voluntarios:** la cobertura es desigual. Restaurantes y estaciones están bien mapeados; oficinas y coworkings, mal (en Atocha, OSM tenía 2 coworkings frente a 9 en Foursquare). Por eso el aviso de los indicadores dice que «OpenStreetMap puede no tener todos los lugares, sobre todo oficinas».
- **Duplicados:** un mismo sitio puede estar como punto, edificio o relación, o con dos nombres (en Atocha, 3 registros del mismo hotel). Los indicadores cuentan una sola vez los lugares con el mismo nombre o la misma web a menos de 200 m.
- **Lento y a veces saturado:** una consulta tarda unos 35 s, más por la tarde, y a veces da 502 o 504. Los servidores de reserva gratuitos de la wiki de OSM no respondieron (22 oct).
- **Precio, reseñas y horarios fiables no están** en OSM.

**Cómo lo manejamos:**

- Un reintento tras 5 s y un **presupuesto de 110 s** por llamada, para contestar siempre antes del corte de 150 s del cliente MCP.
- Si Overpass falla, se usan los **datos guardados** (`from_cache: true` y su fecha de captura). Si no los hay, error claro `[source_unavailable]`. Un fallo nunca se convierte en «0 resultados».
- **Modo demo** (`DEMO_MODE=true`): siempre datos guardados. Lo activa una persona antes de arrancar, nunca el modelo.
- **Capturas:** `data/demo_osm/` (competidores) y `data/demo_osm/audience/` (indicadores) de Atocha y Delicias, con radio de 2.000 m y filtradas por distancia para cualquier radio. Se rehacen con `scripts/capture_osm_demo.py` y `scripts/capture_audience_demo.py`.

## 2. Foursquare Places API

**Qué es.** Base de datos comercial de lugares. Las categorías las ponen sus usuarios.

**Qué usamos.** Solo para **coworkings** y solo **en directo**: completa lo que falta en OSM. Endpoint `places-api.foursquare.com/places/search` (versión `2025-06-17`), hasta 50 resultados.

**Términos de uso:**

- **No se pueden guardar sus datos**, solo el identificador del lugar. Por eso no hay capturas de Foursquare: en modo demo, con datos guardados o si falla, se usa solo OSM.
- Hay que mostrar **«Powered by Foursquare»** cuando se usan sus datos. Está en el campo `attribution` y en el pie del PDF cuando `foursquare_status` es `used`.
- La clave (`FOURSQUARE_API_KEY`) vive solo en el `.env` de cada persona y la lee el propio servidor como `SecretStr`, para que nunca salga en los logs.

**Límites que hemos visto:**

- Varias «coworkings» eran **sedes de empresas** (Repsol, IBM…), porque las categorías las ponen sus usuarios.
- Solo devuelve 50 resultados: si llega a 50, `foursquare_limit_reached: true` avisa de que puede haber más.

**Cómo lo manejamos:**

- Se combina con OSM **sin repetir locales** (nombre que coincide a ≤ 75 m).
- Lo que sale **solo en Foursquare** lleva `needs_review: true` y un motivo (`review_reason`). El sistema no descarta nada: **decide el analista**. La respuesta separa `confirmed_count` y `needs_review_count`, y el agente debe informar de los dos grupos por separado.
- Si no se consultó Foursquare, el servidor añade `coverage_note`: «No se consultó Foursquare: puede haber más coworkings de los listados».
- Cada campo se valida y las categorías también pasan por el filtro anti prompt injection. Si la respuesta está rota, se sigue solo con OSM (`foursquare_status: "failed"`).

## 3. Webs públicas (servidor MCP `fetch`)

**Qué es.** El servidor MCP oficial `mcp-server-fetch` (Anthropic, licencia MIT). Descarga una página web.

**Qué usamos.** El Researcher puede leer webs públicas de la competencia: cartas, tarifas, servicios.

**Términos y límites:**

- **Respeta el `robots.txt`** de cada web: si una web no permite la lectura automática, no se lee.
- Versión fijada (`2026.10.24`) que **rechaza direcciones privadas o internas** (protección SSRF).
- Pedimos el HTML en bruto y lo convertimos a texto nosotros (`html_text.py`), porque su conversor fallaba en Windows dentro de MCP.
- El agente solo puede pedir `url` y `max_length`. Todo el texto pasa por el filtro anti prompt injection: es la fuente con más riesgo de manipulación.
- Muchas webs no publican precios («pide presupuesto») o bloquean la lectura: el dato queda como «sin dato».
- Hoy el Researcher casi no usa `fetch` para tarifas; está anotado como mejora de la tarea.

## 4. Fotos que sube la persona usuaria (agente de visión)

**Qué es.** La consultora sube fotos JPEG o PNG (de locales de la competencia, de una carta…). La herramienta `analyse_image` las analiza con el modelo (Gemini acepta imágenes).

**Qué da:** observaciones por categoría (ambiente, precios, oferta, espacio de trabajo, capacidad, exterior) con su confianza (alta, media o baja), el texto visible y, desde el 29 oct, los **precios de cartas como datos**, que se muestran en una tabla Producto / Tamaño / Precio.

**Términos y cuidados:**

- La foto debe ser **de quien la sube o con permiso**. En la demo de clase se citan la web, el autor y la licencia de cada foto.
- Antes de enviarla al modelo: la ruta debe estar dentro de `outputs/`, máximo 10 MB, JPEG o PNG de verdad (Pillow), reducida a 1.600 px y **sin metadatos** (se borra la posición GPS).
- **Nunca se describe a las personas:** solo se marca si aparecen.
- La imagen se envía al proveedor del modelo (Google Gemini). Según sus condiciones, en el nivel gratuito Google puede usar los datos para mejorar sus productos: con fotos de clientes reales habría que usar el nivel de pago. *(Revisar las condiciones vigentes antes de la entrega.)*

**Límites:**

- La misma foto no siempre da el mismo resultado. Una foto mala (lejana, con reflejos) baja la confianza.
- Lo que ve el modelo puede estar mal leído: las observaciones llevan su confianza y la imagen de la que salen, y el analista puede abrir la foto para comprobarlo.

## 5. Datos que aporta la persona usuaria

Presupuesto, superficie, radio, notas de contexto (formulario) y lo que se añade en el chat. Se registran como fuente `user_input`, y las notas se anonimizan antes de usarlas (correos, teléfonos, DNI/NIE, nombres y URL). Son la base del cálculo del punto de equilibrio: **sin alquiler, costes y precios, el Analista no puede calcularlo** y lo dice.

## 6. El modelo de lenguaje no es una fuente

Gemini (`gemini-3.5-flash-lite`, issue #4) razona y redacta, pero **no aporta datos**: una cifra que no venga de una herramienta o de la persona usuaria no puede aparecer en el informe. Los agentes tienen la regla «no inventes, escribe sin dato».

## Fuentes que no usamos (y por qué)

| Fuente | Motivo | Estado |
| --- | --- | --- |
| Google Places API | Coste y facturación; sus términos solo permiten guardar `place_id` (y coordenadas, 30 días), así que no habría modo demo | Roadmap |
| Reseñas de Google, Tripadvisor… | Sin API gratuita; leerlas automáticamente va contra sus términos | Roadmap: campo opcional para que la persona usuaria pegue reseñas, o Google Places |
| Portales de alquiler (Idealista…) | Sin API abierta; leerlos automáticamente va contra sus términos | Lo introduce la persona usuaria |
| Datos abiertos del Ayuntamiento de Madrid (padrón por barrio, renta…) | No dio tiempo a revisar formato y licencia | Roadmap: completaría los indicadores de público con edades y renta |
| Servidor Overpass con clave o base de datos propia | Para producción | Roadmap: extracto de OSM de Madrid en PostgreSQL + PostGIS, actualizado cada noche |

## Fechas y caducidad

- Todo dato lleva `retrieved_at` (cuándo se leyó). En los datos guardados es la **fecha de captura**, nunca «ahora», y el informe debe decirlo («datos guardados el 22/10/2026»).
- Capturas de competidores: 22 oct 2026. Capturas de indicadores de público: 28 oct 2026.
- Conviene repetir las capturas antes de la demo si han pasado varias semanas.