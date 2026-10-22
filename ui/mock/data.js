export const MOCK_DEBATE = [
  {
    agent:   "researcher",
    name:    "Investigador",
    role:    "Análisis de mercado",
    message: "He analizado 14 negocios similares en un radio de 1 km alrededor de Atocha. La densidad de cafeterías con coworking es moderada: solo 3 ofrecen tanto café de especialidad como puestos de trabajo fijos. El precio medio de alquiler en la zona es de 22 €/m².",
    delay: 800,
  },
  {
    agent:   "analyst",
    name:    "Analista",
    role:    "Viabilidad financiera",
    message: "Con 120 m² y un alquiler estimado de 2.640 €/mes, el punto de equilibrio requiere ingresar al menos 9.800 €/mes. Asumiendo un ticket medio de 8 € y una tasa de ocupación del 60%, se necesitan unos 51 clientes diarios. Es alcanzable en temporada alta, pero ajustado en agosto.",
    delay: 2200,
  },
  {
    agent:   "vision",
    name:    "Especialista Visual",
    role:    "Análisis de imágenes",
    message: "He analizado 8 fotos de locales competidores en Atocha. Observaciones: el 75% tienen mesas pequeñas sin espacio para portátil, solo 1 muestra regletas de corriente visibles. Los espacios con mejor puntuación en reseñas muestran luz natural abundante y separación acústica entre zona cafetería y zona trabajo. Ninguno ofrece cabinas privadas. Oportunidad de diferenciación clara en equipamiento de trabajo.",
    delay: 3200,
  },
  {
    agent:   "writer",
    name:    "Redactor",
    role:    "Síntesis del informe",
    message: "El análisis muestra una oportunidad real pero con margen estrecho. La diferenciación debería centrarse en la comunidad de usuarios y en eventos temáticos que generen ingresos fuera del horario de coworking. Propongo destacar esto en el informe como palanca de crecimiento.",
    delay: 5000,
  },
  {
    agent:   "reviewer",
    name:    "Revisor",
    role:    "Control de calidad",
    message: "He revisado las cifras. La estimación de ocupación del 60% es optimista para el primer año; recomendaría usar 45% en el escenario base. Con ese ajuste el punto de equilibrio sube a 68 clientes diarios, lo que lo convierte en viable con riesgo medio. El semáforo debería ser amarillo, no verde.",
    delay: 7000,
  },
  {
    agent:   "analyst",
    name:    "Analista",
    role:    "Viabilidad financiera",
    message: "Acepto la corrección del Revisor. Con el 45% de ocupación el margen baja a 3,2%, que es viable pero exige control estricto de costes variables. Confirmo: viabilidad media-alta, confianza 72%.",
    delay: 8600,
  },
];

// Shape mirrors the real API response (schemas.Verdict.model_dump() with computed fields)
export const MOCK_VERDICT = {
  light:            "amber",
  confidence:       0.72,
  summary:          "Viabilidad media — riesgo controlado",
  reasons: [
    "Demanda confirmada: 3 competidores directos con valoración media de 4,2 ★",
    "Punto de equilibrio alcanzable con 68 clientes/día en escenario base (45% ocupación)",
    "Riesgo estacional: agosto puede caer un 35% en afluencia",
    "Diferenciación insuficiente frente a WeWork Atocha sin propuesta de comunidad clara",
  ],
  missing_data:     [],
  final_light:      "amber",
  final_confidence: 0.72,
};
