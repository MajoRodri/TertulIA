# Arquitectura de TertulIA

Este documento explica cómo está construido TertulIA y cómo viaja un estudio de mercado desde que la persona lo pide hasta que descarga el informe. Tiene tres diagramas, de lo general a lo concreto:

1. **Vista general:** qué piezas hay y cómo se conectan.
2. **Recorrido de un estudio:** qué pasa en cada uno de los 5 pasos de la interfaz.
3. **El grafo de LangGraph:** cómo se controla el bucle de revisión y la aprobación humana.

Al final hay una tabla con las decisiones de diseño y las limitaciones conocidas.

> Los diagramas describen el código de la rama `dev` a 3 de noviembre de 2026 (tras los PR #88 y #90). Si el código cambia, este documento debe actualizarse en el mismo PR.

---

## 1. Vista general

```mermaid
flowchart TB
    U(["Persona usuaria<br/>analista o emprendedor"])

    subgraph APP["Aplicación TertulIA"]
        direction TB
        UI["Interfaz web<br/>HTML + CSS + JS"]
        API["API FastAPI<br/>coordina el estudio"]
        GR["Guardarraíles<br/>anti prompt injection<br/>y anonimización"]
        GRAPH["Grafo de control<br/>LangGraph"]
        PDF["Generador<br/>del informe PDF"]
        UI <--> API
        API --> GR
        API <--> GRAPH
        API --> PDF
    end

    subgraph AG["Equipo de 5 agentes · CrewAI · herramientas de solo lectura"]
        direction LR
        A1["<b>La Portera</b> · Investigadora<br/>MCP neighbourhood_data<br/>MCP fetch"]
        A2["<b>Berto</b> · Visión<br/>analyse_image"]
        A3["<b>El Chulapo</b> · Analista<br/>break_even<br/>run_python"]
        A4["<b>El Pregonero</b> · Redactor<br/>sin herramientas"]
        A5["<b>La Revisora</b> · Revisión<br/>sin herramientas"]
    end

    subgraph EXT["Servicios externos"]
        direction LR
        LLM["Google Gemini<br/>razonamiento de los agentes"]
        OSM["OpenStreetMap<br/>Overpass API"]
        FSQ["Foursquare<br/>Places API"]
    end

    subgraph DISK["Disco local"]
        direction LR
        CACHE[("Capturas guardadas<br/>si OSM falla")]
        CKP[("Estado del grafo<br/>checkpoints.db")]
        TRZ[("Trazas de auditoría<br/>trazas/")]
    end

    U <--> APP
    APP -- "lanza a los agentes" --> AG
    AG -- "consultan" --> EXT
    APP -- "guarda" --> DISK

    classDef soft fill:#F5F6FA,stroke:#7580A0,color:#0F1730
    class LLM,OSM,FSQ,CACHE,CKP,TRZ soft
```

**Cómo leerlo:**

- La **API** es el centro: recibe el encargo de la interfaz, lanza a los agentes, controla el grafo y genera el PDF.
- **Solo dos agentes traen datos de fuera.** La Portera consulta OpenStreetMap y Foursquare a través del servidor MCP propio (`neighbourhood_data`), y webs públicas con el servidor MCP `fetch`. Berto analiza las fotos que sube la persona. Si OpenStreetMap no responde, el servidor usa las capturas guardadas e indica su fecha.
- **El Pregonero y la Revisora no tienen herramientas:** solo trabajan con lo que reciben, para que no puedan traer cifras sin fuente.
- **Todas las herramientas son de solo lectura.** Ninguna envía, publica ni borra nada.
- Todo el texto que llega de fuera (webs, nombres de locales, texto de fotos, documentos y chat) pasa por los **guardarraíles** antes de llegar a un agente.

---

## 2. Recorrido de un estudio

Los 5 pasos son los mismos que ve la persona en la interfaz.

```mermaid
sequenceDiagram
    autonumber
    actor P as Persona
    participant UI as Interfaz
    participant API as API FastAPI
    participant C as Agentes CrewAI
    participant G as Grafo LangGraph
    participant L as Gemini

    Note over P,L: Paso 1 · Encargo
    P->>UI: Sector, barrio, presupuesto, fotos, documentos
    UI->>API: POST /api/analyze
    API->>API: Anonimiza las notas y valida el encargo

    Note over P,L: Paso 2 · Debate
    UI->>API: GET /api/debate (los mensajes llegan en directo)
    API->>C: Investigación y visión (en paralelo)
    C->>L: Cada agente razona con Gemini
    API->>C: Análisis, después redacción, después revisión
    API-->>UI: Mensaje de cada agente
    API->>G: Inicia el grafo con los resultados
    G->>L: Revisora y Redactor (bucle, máximo 3 rondas)
    G-->>API: Se para antes de la aprobación humana

    Note over P,L: Paso 3 · Contexto (opcional)
    P->>UI: Aporta datos en el chat o sube documentos
    UI->>API: POST /api/chat
    API->>L: Respuesta del chat (sin herramientas)

    Note over P,L: Paso 4 · Veredicto
    UI->>API: GET /api/verdict
    API->>C: Si hubo chat, el Redactor reescribe con ese contexto
    API->>API: Lee la línea SEMAFORO y calcula la confianza
    API-->>UI: Semáforo, resumen, motivos y tokens

    Note over P,L: Paso 5 · Aprobar
    P->>UI: Aprueba (o rechaza)
    UI->>API: POST /api/approve
    API->>G: Reanuda el grafo con la decisión
    G-->>API: Registra la decisión humana
    API->>API: Guarda las trazas y genera el PDF
    API-->>P: Descarga del informe
```

**Lo importante de este recorrido:**

- **Nada sale del sistema sin aprobación humana.** El PDF solo se genera en el paso 5, después de que la persona apruebe.
- El veredicto que se aprueba en el paso 4 es **el mismo** que aparece en el PDF.

---

## 3. El grafo de LangGraph

El grafo es el que decide cuándo repetir, cuándo parar y cuándo esperar a una persona.

```mermaid
flowchart TD
    START((Inicio)) --> R["research<br/>recibe la investigación"]
    R --> A["analyst<br/>recibe el análisis"]
    A --> V["vision_charts<br/>analiza gráficos si los hay"]
    V --> W["writer<br/>Redactor"]
    W --> RV["reviewer<br/>Revisora"]

    RV --> D1{"¿Hay comentarios<br/>y quedan rondas?<br/>máximo 3"}
    D1 -- "Sí" --> W
    D1 -- "No, o error grave" --> PAUSA

    PAUSA[["PAUSA<br/>espera a la persona"]] --> H["human_approval<br/>registra aprobar,<br/>rechazar o caducar"]

    H --> D2{"¿Hay contexto del chat<br/>sin aplicar?"}
    D2 -- "Sí" --> W
    D2 -- "No" --> FIN((Fin))

    CTRL["En cada nodo:<br/>si se agota el presupuesto de tokens<br/>o hay un error grave,<br/>se registra y se va a la aprobación"]
    CTRL -.- RV

    classDef pausa fill:#FEF9C3,stroke:#EAB308,color:#0F1730
    classDef decision fill:#EEF2FF,stroke:#2B4EFF,color:#0F1730
    class PAUSA pausa
    class D1,D2 decision
```

**Cómo leerlo:**

- **Bucle de revisión:** si la Revisora pide cambios, el Redactor reescribe con sus comentarios. Como máximo 3 rondas (`MAX_ITERATIONS` en `config/settings.py`).
- **Pausa humana:** el grafo se detiene justo antes de `human_approval` (`interrupt_before`). Su estado se guarda en `checkpoints.db`, y la API lo reanuda cuando la persona decide.
- **Errores graves:** si se agota el presupuesto de tokens (`ERR-006`) o falla un nodo (`ERR-008`), el grafo deja de repetir y va directo a la aprobación humana. Si la persona no responde en 24 h, el estudio caduca (`ERR-009`). Detalle en `docs/errores.md`.

---

## 4. Decisiones de diseño y limitaciones conocidas

| Tema | Cómo es | Por qué | Limitación conocida |
|---|---|---|---|
| CrewAI + LangGraph | CrewAI define los agentes; LangGraph controla el flujo, el bucle y la pausa | Autonomía controlada: el grafo decide, no un agente jefe. Ver `docs/decisiones/0002-proceso-crewai.md` | — |
| Dónde se ejecutan los agentes | Investigación, visión y análisis se ejecutan en la API durante el debate; Redactor y Revisora se ejecutan dentro del grafo | Mostrar los mensajes del debate en directo en la interfaz | Los nodos `research` y `analyst` del grafo solo reciben los datos ya calculados |
| Bucle de revisión | Revisora real, hasta 3 rondas | Que el informe se revise antes de llegar a la persona | La versión reescrita en el bucle no cambia el veredicto ni el PDF, y la Revisora no recibe la investigación ni el análisis completos |
| Semáforo | El Redactor termina con `SEMAFORO: VERDE`, `AMBAR` o `ROJO`, y el código lee esa línea | Evitar deducir el color buscando palabras en el texto | Es una instrucción al modelo: si no escribe la línea, se usa una búsqueda de palabras menos fiable |
| Regla del ámbar | Rojo solo si los números demuestran inviabilidad; ámbar si faltan datos críticos | "No viable" y "no lo sabemos" no son lo mismo (`docs/etica-y-gobernanza.md`) | Depende de que el modelo siga la instrucción |
| Confianza | 1 menos un 10 % por cada "sin dato" del informe y un 5 % por cada fuente sospechosa | Fórmula fija y reproducible | Cuenta la expresión "sin dato" en el texto, no los datos que faltan: puede salir 100 % aunque falten datos |
| Fuentes de datos | OpenStreetMap y Foursquare por MCP; capturas guardadas si OSM falla | Datos reales con fuente y fecha; la demo funciona aunque Overpass caiga | OSM tiene poca cobertura de oficinas y coworkings |
| Trazas | `trazas/<job_id>/traces.jsonl` | Que un tercero pueda auditar la decisión | Hoy registran la decisión humana, no las acciones de cada agente |
| Estado | Grafo en `checkpoints.db`; datos del estudio en memoria de la API | Que el grafo pueda pausarse y reanudarse | Si el servidor se reinicia, los estudios en curso se pierden |
| Modelo | Gemini `gemini-3.5-flash-lite`, configurable en `.env` | Capa gratuita y respuesta rápida | La visión usa el formato de mensajes de Gemini |
