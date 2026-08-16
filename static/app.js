async function postJSON(url) {
  const response = await fetch(url, { method: "POST" });
  let payload = {};
  try {
    payload = await response.json();
  } catch (err) {
    payload = { ok: false, error: `HTTP ${response.status}` };
  }
  return payload;
}

document.addEventListener("click", async (event) => {
  const row = event.target.closest("tr[data-lead-id]");
  if (!row) return;
  const leadId = row.dataset.leadId;

  if (event.target.classList.contains("send-btn")) {
    const button = event.target;
    button.disabled = true;
    button.textContent = "Sending...";
    const result = await postJSON(`/leads/${leadId}/send`);
    if (result.ok) {
      row.querySelector(".contacted").textContent = "Yes";
      button.textContent = "Sent";
    } else {
      button.textContent = "Retry";
      button.disabled = false;
      alert(`Send failed: ${result.error}`);
    }
  }

  if (event.target.classList.contains("delete-btn")) {
    if (!confirm("Delete this lead?")) return;
    const result = await postJSON(`/leads/${leadId}/delete`);
    if (result.ok) {
      row.remove();
    } else {
      alert(`Delete failed: ${result.error}`);
    }
  }
});
