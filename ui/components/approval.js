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
        triggerDownload(result, `report_tertulia_${jobId}.pdf`);
        btnApprove.textContent = "✓ Informe descargado";
      } else {
        btnApprove.disabled = false;
        btnApprove.textContent = result.reason === "estudio caducado"
          ? "Estudio caducado — inicia un análisis nuevo"
          : `Error: ${result.reason ?? "no se pudo generar el informe"}`;
      }
    } catch (err) {
      btnApprove.disabled = false;
      btnApprove.textContent = "Aprobar y descargar informe";
      console.error(err);
    }
  });

  btnReject.addEventListener("click", async () => {
    await approveReport(jobId, false).catch(() => {});
    document.getElementById("panel-approval").classList.add("hidden");
    document.getElementById("panel-debate").scrollIntoView({ behavior: "smooth" });
  });
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a   = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}
