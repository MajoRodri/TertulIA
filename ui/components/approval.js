import { approveReport } from "../api.js";

export function initApproval(jobId) {
  const btnApprove = document.getElementById("btn-approve");
  const btnReject  = document.getElementById("btn-reject");

  btnApprove.addEventListener("click", async () => {
    btnApprove.disabled = true;
    btnApprove.textContent = "Generando informe…";
    try {
      const result = await approveReport(jobId);
      if (result instanceof Blob) {
        const filename = jobId === "demo-001" ? "informe_demo.pdf" : "InformeTertulIA.pdf";
        triggerDownload(result, filename);
        btnApprove.textContent = "✓ Informe descargado";
      } else {
        btnApprove.disabled = false;
        const reason = result.reason ?? result.status ?? "error desconocido";
        btnApprove.textContent = reason === "estudio caducado"
          ? "Estudio caducado. Inicia un análisis nuevo"
          : `No se pudo generar el informe: ${reason}`;
        btnApprove.title = result.reason ?? result.status ?? "error desconocido";
      }
    } catch (err) {
      btnApprove.disabled = false;
      btnApprove.textContent = "Error al conectar. Inténtalo de nuevo.";
      btnApprove.title = err.message;
      console.error("approve error:", err);
    }
  });

  btnReject.addEventListener("click", async () => {
    if (!confirm("¿Seguro que quieres rechazar el análisis? Volverás al debate para ajustar los datos.")) return;
    await approveReport(jobId, false).catch(() => {});
    document.getElementById("panel-approval").classList.add("hidden");
    document.getElementById("panel-debate").classList.remove("hidden");
  });
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a   = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}
