# Arranca el servidor de desarrollo de TertulIA.
# --timeout-graceful-shutdown 3: Ctrl+C mata el proceso en ≤ 3 s aunque
# haya hilos de CrewAI bloqueados esperando respuesta de Gemini.

.\.venv\Scripts\Activate.ps1
uvicorn src.tertulia.api.main:app `
  --reload `
  --reload-dir src `
  --port 8000 `
  --timeout-graceful-shutdown 3
