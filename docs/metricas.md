# Métricas: chat normal vs TertulIA

Dueña: Yohanna · Issue #28 · Revisa: Helen · **Prueba el 3 de noviembre** (tras congelar funcionalidades).

> Regla del tribunal: «nada de cifras de memoria». Esta página solo contiene números
> que hayamos **medido nosotras** o que tengan **fuente citada**. Hasta que se mida,
> las tablas quedan vacías: no rellenar con estimaciones.

## Qué queremos demostrar
Que TertulIA aporta algo que un chat normal no: fuentes verificables, cálculos
reproducibles (código/herramienta), revisión del Revisor, semáforo con confianza y
aprobación humana. Y, por separado, comprobar las cifras del dossier («3 semanas»,
«más de 1.000 €» para un estudio manual).

## Protocolo (idéntico para ambos sistemas)
1. **Encargo único**, fijado antes de empezar y guardado aquí: sector `cafe_cowork`,
   barrio Atocha, presupuesto y perfil `analista`.
2. **Chat normal**: un modelo sin herramientas, prompt = el encargo en una frase. Una sola
   pasada, sin repreguntas. Guardar la respuesta íntegra en `docs/metricas/chat_normal.md`.
3. **TertulIA**: mismo encargo desde la interfaz, con la demo completa. Guardar informe y
   traza (`outputs/`) en `docs/metricas/tertulia.md`.
4. **Mismo modelo** en ambos si es posible (decisión en `docs/decisiones/0001-modelo-y-claves.md`).
5. Repetir **3 veces** cada sistema y registrar los tres resultados (el LLM varía).
6. Puntuar las respuestas **sin saber cuál es cuál** (que puntúe otra persona, no la que lanzó la prueba).

## Métricas
| Métrica | Cómo se mide | Chat normal | TertulIA |
|---|---|---|---|
| Afirmaciones con fuente citada | nº de afirmaciones con fuente comprobable / nº total de afirmaciones con datos | | |
| Fuentes que existen y dicen lo que se afirma | se abren una a una (enlace + fecha) | | |
| Cifras sin respaldo | cifras del informe sin fuente ni código que las produzca | | |
| Cálculos reproducibles | cálculos que se pueden repetir con el código/herramienta registrado | | |
| Datos que faltaban y se declararon | casos de «sin dato» señalados vs. inventados | | |
| Tiempo hasta el informe | cronómetro, en minutos | | |
| Coste en tokens | del log de `trazas/` (chat normal: de la API) | | |
| Revisión humana posible | ¿hay punto de aprobación antes de entregar? sí/no | | |

## Registro de ejecuciones
| Fecha | Sistema | Modelo | Ejecución nº | Quién puntúa | Enlace a la salida |
|---|---|---|---|---|---|
| | | | | | |

## Cifras del dossier a respaldar
| Cifra | ¿Medida o citada? | Fuente / medición | Estado |
|---|---|---|---|
| «3 semanas» (estudio manual) | | | pendiente |
| «más de 1.000 €» (estudio manual) | | | pendiente |

Si no se consigue fuente o medición, **quitar la cifra del dossier** o reformularla sin número.

## Limitaciones (escribirlas tal cual en la presentación)
- Muestra pequeña (un encargo, 3 repeticiones): es una prueba orientativa, no un estudio.
- La puntuación tiene un componente subjetivo; por eso se hace a ciegas y se publican las salidas.
