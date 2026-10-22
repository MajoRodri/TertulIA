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
// Each event: { agent, name, role, message } | { done: true }
export function openDebateStream(jobId, onMessage, onDone, onError) {
  if (USE_MOCK) {
    simulateMockStream(onMessage, onDone);
    return () => {};
  }
  const es = new EventSource(`${API_BASE}/api/debate/${jobId}`);
  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.done) { es.close(); onDone(); }
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

// POST /api/approve/{jobId}  →  PDF blob
export async function approveReport(jobId) {
  if (USE_MOCK) return mockPDFBlob();
  const res = await fetch(`${API_BASE}/api/approve/${jobId}`, { method: "POST" });
  if (!res.ok) throw new Error(`Error ${res.status} approving report`);
  return res.blob();
}

// ── Mock helpers ──────────────────────────────────────────────
function simulateMockStream(onMessage, onDone) {
  MOCK_DEBATE.forEach((msg) => setTimeout(() => onMessage(msg), msg.delay));
  const lastDelay = MOCK_DEBATE[MOCK_DEBATE.length - 1].delay;
  setTimeout(onDone, lastDelay + 600);
}

function mockPDFBlob() {
  const raw = `%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF`;
  return new Blob([raw], { type: "application/pdf" });
}
