import { API_BASE, USE_MOCK } from "./config.js";
import { MOCK_DEBATE, MOCK_VERDICT } from "./mock/data.js";

// POST /api/analyze  →  { job_id: string }
export async function startAnalysis(brief) {
  if (USE_MOCK) return { job_id: "demo-001" };
  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(brief),
  });
  if (!res.ok) throw new Error(`Error ${res.status} starting analysis`);
  return res.json();
}

// GET /api/debate/{jobId}  →  SSE stream
// Each event: { agent, name, role, message } | { paused: true }
export function openDebateStream(jobId, onMessage, onDone, onError) {
  if (USE_MOCK) {
    simulateMockStream(onMessage, onDone);
    return () => {};
  }
  const es = new EventSource(`${API_BASE}/api/debate/${jobId}`);
  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.paused) { es.close(); onDone(); }
    else onMessage(data);
  };
  es.onerror = () => { es.close(); onError?.(new Error("SSE connection error")); };
  return () => es.close();
}

// GET /api/verdict/{jobId}  →  { signal, label, confidence, reasons }
export async function fetchVerdict(jobId) {
  if (USE_MOCK) return MOCK_VERDICT;
  const res = await fetch(`${API_BASE}/api/verdict/${jobId}`);
  if (!res.ok) throw new Error(`Error ${res.status} fetching verdict`);
  return res.json();
}

// POST /api/approve/{jobId}  →  PDF blob (approved=true) or { ok, status } (approved=false)
export async function approveReport(jobId, approved = true) {
  const res = await fetch(`${API_BASE}/api/approve/${jobId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved }),
  });
  if (!res.ok) throw new Error(`Error ${res.status} approving report`);
  const ct = res.headers.get("Content-Type") ?? "";
  return ct.includes("application/pdf") ? res.blob() : res.json();
}

// POST /api/upload/{jobId}  →  { paths: string[] }
export async function uploadImages(jobId, files) {
  if (USE_MOCK || !files.length) return { paths: [] };
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const res = await fetch(`${API_BASE}/api/upload/${jobId}`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Error ${res.status} uploading images`);
  return res.json();
}

// GET /api/vision/{jobId}  →  SSE stream of Berto's image analysis (may be empty)
export function openVisionStream(jobId, onMessage, onDone, onError) {
  if (USE_MOCK) { onDone(); return () => {}; }
  const es = new EventSource(`${API_BASE}/api/vision/${jobId}`);
  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.done) { es.close(); onDone(); }
    else onMessage(data);
  };
  es.onerror = () => { es.close(); onError?.(new Error("SSE error")); };
  return () => es.close();
}

// POST /api/chat/{jobId}  →  SSE stream of agent responses
export async function sendChatMessage(jobId, message, files, onMessage) {
  if (USE_MOCK) {
    return simulateMockChatResponse(onMessage);
  }
  const form = new FormData();
  form.append("message", message);
  for (const f of (files || [])) form.append("images", f);
  const res = await fetch(`${API_BASE}/api/chat/${jobId}`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(`Error ${res.status} sending chat message`);
  const reader  = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = JSON.parse(line.slice(6));
        if (!data.done) onMessage(data);
      }
    }
  }
}

// ── Mock helpers ──────────────────────────────────────────────
function simulateMockStream(onMessage, onDone) {
  MOCK_DEBATE.forEach((msg) => setTimeout(() => onMessage(msg), msg.delay));
  const lastDelay = MOCK_DEBATE[MOCK_DEBATE.length - 1].delay;
  setTimeout(onDone, lastDelay + 600);
}

async function simulateMockChatResponse(onMessage) {
  const responses = [
    { agent: "analyst", name: "Analista", role: "Viabilidad financiera",
      message: "Gracias por el dato adicional. He recalculado las proyecciones teniendo en cuenta lo que comentas. Actualizaré el escenario base antes del veredicto final." },
    { agent: "reviewer", name: "Revisor", role: "Control de calidad",
      message: "Incorporo el contexto en la valoración. Ajusto la confianza y los motivos del veredicto en consecuencia." },
  ];
  for (const msg of responses) {
    await new Promise((r) => setTimeout(r, 1200));
    onMessage(msg);
  }
}

function mockPDFBlob() {
  const raw = `%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF`;
  return new Blob([raw], { type: "application/pdf" });
}
