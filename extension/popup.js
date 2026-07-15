document.addEventListener("DOMContentLoaded", () => {
  const dot = document.getElementById("status-dot");
  const statusText = document.getElementById("status-text");
  const alertsDiv = document.getElementById("alerts");
  fetch("http://localhost:8000/api/messages?limit=5")
    .then((r) => r.json())
    .then((data) => {
      if (Array.isArray(data) && data.length > 0) {
        dot.className = "dot online";
        statusText.textContent = "Connected";
        alertsDiv.innerHTML = "";
        for (const msg of data) {
          const div = document.createElement("div");
          div.className = "alert";
          div.textContent = msg.summary || msg.text || JSON.stringify(msg);
          alertsDiv.appendChild(div);
        }
      }
    })
    .catch(() => {
      dot.className = "dot offline";
      statusText.textContent = "Disconnected";
    });
  document.getElementById("check-now").addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "CHECK_MESSAGES" });
  });
});
