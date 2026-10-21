# data/demo_atocha/ — respuestas guardadas para la demo sin internet

Dueña: Yohanna · Issue #26 · **Plazo: antes del 23 de octubre** (las demás trabajan con esto).

## Cómo rellenarla
1. Conseguir las claves (issue #4) y ponerlas en `.env` (nunca en git).
2. Leer los términos de uso de cada API y anotar los límites en `docs/fuentes-de-datos.md`.
3. `python data/demo_atocha/capture_demo.py --source all`
4. Comprobar `manifest.json` (fecha de captura y de caducidad) y hacer commit.

## Qué se guarda y por qué
| Fichero | Contenido | Nota |
|---|---|---|
| `foursquare_cafes.json`, `foursquare_coworking.json` | Respuesta de `/places/search` | Revisar términos de Foursquare antes de publicar |
| `google_cafes.json`, `google_coworking.json` | Solo `id` + `location` | Los términos de Google solo permiten guardar place_id y coordenadas (30 días máx.) |
| `manifest.json` | Fechas de captura/caducidad (`captured_at`, `expires_at`) | Lo actualiza el script |

## Pendiente de hacer a mano (no lo captura el script)
- **Datos abiertos del Ayuntamiento de Madrid** (población, renta, flujo, etc. del distrito Retiro/Arganzuela/Centro): descargar los CSV que decidan Helen y María Isabel y guardarlos aquí con su URL y fecha en `manifest.json`.
- **Alquiler del local**: si no hay API de portales (riesgo del plan), valor introducido a mano o informe público por distrito, siempre con fuente.

## Cómo encaja con los schemas
- `captured_at` del manifest es lo que el grafo guarda en `Source.retrieved_at`.
- Todo lo que se lea de estos ficheros se marca `Source.from_cache = True`.
- Antes de usar una captura de Google, comprobar que `expires_at` no ha pasado.

## Regla para los tests
Los tests **no** deben depender de estos ficheros reales (pueden caducar): usad datos sintéticos dentro de `tests/`.
