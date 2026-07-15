let ws = null;
let isSpeaking = false;

function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  try {
    ws = new WebSocket("ws://localhost:8000/ws");
    ws.onopen = () => console.log("Vigil: WebSocket connected");
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "alert" && data.summary && !isSpeaking) {
          isSpeaking = true;
          chrome.tts.speak(data.summary, {
            onEvent: (evt) => {
              if (evt.type === "end" || evt.type === "error" || evt.type === "interrupted") {
                isSpeaking = false;
              }
            },
          });
        }
      } catch (e) {
        console.error("Vigil: WS message parse error", e);
      }
    };
    ws.onclose = () => {
      ws = null;
      setTimeout(connectWebSocket, 5000);
    };
    ws.onerror = () => {
      ws?.close();
    };
  } catch (e) {
    setTimeout(connectWebSocket, 5000);
  }
}

connectWebSocket();

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === "NEW_MESSAGES") {
    for (const msg of request.messages) {
      fetch("http://localhost:8000/api/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(msg),
      }).catch((err) => console.error("Vigil: POST error", err));
    }
    sendResponse({ success: true });
  } else if (request.type === "CHECK_MESSAGES") {
    fetch("http://localhost:8000/api/messages?important=true&limit=5")
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data) && data.length > 0 && !isSpeaking) {
          const text = data.map((m) => m.summary || m.text).join(". ");
          isSpeaking = true;
          chrome.tts.speak(text, {
            onEvent: (evt) => {
              if (evt.type === "end" || evt.type === "error" || evt.type === "interrupted") {
                isSpeaking = false;
              }
            },
          });
        }
      })
      .catch((err) => console.error("Vigil: GET error", err));
    sendResponse({ success: true });
  }
  return true;
});
