# 0001 · Modelo de lenguaje y claves de API

Estado: **pendiente — decidir en la próxima reunión** · Issue #4 · Responsable de preparar: Yohanna
Decide: el equipo (anotar aquí el resultado y la fecha).

## Qué hay que decidir
1. Modelo **comercial o local**.
2. **Presupuesto máximo de tokens por informe** (hoy `.env.example` propone `MAX_TOKENS_POR_INFORME=50000`; es un valor de partida, no una decisión).
3. Si se usa el mismo modelo para los agentes y para la prueba de métricas (`docs/metricas.md`).

## Criterios (rellenar con datos comprobados, no de memoria)
| Criterio | Comercial (API) | Local |
|---|---|---|
| Soporta tool calling fiable (CrewAI + LangGraph + MCP) | | |
| Soporta imágenes (agente multimodal de Helen) | | |
| Coste estimado por informe (con precios vigentes citados) | | |
| Privacidad: ¿salen datos del cliente fuera? (anonimización de Majo) | | |
| Velocidad / latencia en la demo en directo | | |
| Funciona sin internet el día de la presentación | | |
| Esfuerzo de montaje para todas | | |

## Decisión
- Modelo elegido: _
- Motivo: _
- Presupuesto de tokens por informe: _
- Fecha y quién estaba: _

## Claves de API (checklist; las claves **nunca** al repo)
- [ ] Anthropic / OpenAI (según decisión): clave por persona para desarrollo
- [ ] Google Places (API nueva): crear clave y **restringirla a la API de Places** y poner un límite de cuota/presupuesto
- [ ] Foursquare: crear Service Key en el Developer Console
- [ ] Cada una guarda sus claves en su `.env` local (copiado de `.env.example`)
- [ ] Majo añade las claves compartidas como *Secrets* del repo (solo si CI las necesita)
- [ ] Leer términos de uso y anotarlos en `docs/fuentes-de-datos.md` (Helen) antes de llenar `data/demo_atocha/`
