import { approveReport } from "../api.js";

const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function initApproval(jobId) {
  const btnApprove = document.getElementById("btn-approve");
  const btnReject  = document.getElementById("btn-reject");

  btnApprove.addEventListener("click", async () => {
    btnApprove.disabled = true;
    btnApprove.textContent = "Generando informe…";
    try {
      const result = await approveReport(jobId);
      if (result instanceof Blob) {
        triggerDownload(result, `report_tertulia_${jobId}.pdf`);
        btnApprove.textContent = "✓ Informe descargado";
      } else {
        btnApprove.disabled = false;
        const reason = result.reason ?? result.status ?? "error desconocido";
        btnApprove.textContent = reason === "estudio caducado"
          ? "Estudio caducado. Inicia un análisis nuevo"
          : `No se pudo generar el informe: ${reason}`;
        btnApprove.title = JSON.stringify(result);
      }
    } catch (err) {
      btnApprove.disabled = false;
      btnApprove.textContent = "Error al conectar — inténtalo de nuevo";
      btnApprove.title = err.message;
      console.error("approve error:", err);
    }
  });

  btnReject.addEventListener("click", async () => {
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
