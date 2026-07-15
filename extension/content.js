let lastMessageCount = 0;
let keepaliveInterval = null;
let qrCheckInterval = null;

function extractMessages() {
  const messageElements = document.querySelectorAll(
    '[data-testid="conversation-panel-message-body"]'
  );
  if (messageElements.length <= lastMessageCount) return;
  const groupNameEl = document.querySelector(
    '[data-testid="conversation-info-header"] h1'
  );
  const group_name = groupNameEl ? groupNameEl.textContent.trim() : "Unknown Group";
  const messages = [];
  for (let i = lastMessageCount; i < messageElements.length; i++) {
    const el = messageElements[i];
    const senderEl = el.closest('[data-testid="conversation-panel-message"]')?.querySelector(
      '[data-testid="conversation-participant-name"]'
    );
    const sender = senderEl ? senderEl.textContent.trim() : "Unknown";
    messages.push({
      source: "whatsapp",
      group_name,
      sender,
      text: el.textContent.trim(),
    });
  }
  lastMessageCount = messageElements.length;
  return messages;
}

/* ── Keepalive: prevent WhatsApp Web from going idle ── */
function startKeepalive() {
  if (keepaliveInterval) clearInterval(keepaliveInterval);
  keepaliveInterval = setInterval(function() {
    /* Send a lightweight presence ping */
    const pingTarget = document.querySelector('[data-testid="conversation-info-header"]');
    if (pingTarget) {
      /* Touching the DOM is enough to reset the inactivity timer */
      pingTarget.dispatchEvent(new Event('mousemove', { bubbles: true }));
    }
    /* Also check for new messages in case MutationObserver missed something */
    const messages = extractMessages();
    if (messages && messages.length > 0) {
      chrome.runtime.sendMessage({ type: "NEW_MESSAGES", messages });
    }
  }, 60000); /* every 60 seconds */
}

/* ── Detect QR code (session expired) ── */
function startQrDetection() {
  if (qrCheckInterval) clearInterval(qrCheckInterval);
  qrCheckInterval = setInterval(function() {
    const qrCanvas = document.querySelector('canvas');
    const loginTitle = document.querySelector('[data-testid="qrcode"]');
    const hasQr = qrCanvas && (loginTitle || document.body.innerText.includes('Scan this QR code'));
    if (hasQr) {
      chrome.runtime.sendMessage({ type: "SESSION_EXPIRED" });
      clearInterval(qrCheckInterval);
      qrCheckInterval = null;
    }
  }, 5000);
}

/* ── Observer for new messages ── */
const observer = new MutationObserver(() => {
  const messages = extractMessages();
  if (messages && messages.length > 0) {
    chrome.runtime.sendMessage({ type: "NEW_MESSAGES", messages });
  }
});

/* ── Init ── */
function init() {
  /* Wait for WhatsApp Web to fully load */
  const checkReady = setInterval(function() {
    const panel = document.querySelector('[data-testid="conversation-panel-message-body"]');
    if (panel || document.querySelector('[data-testid="qrcode"]')) {
      clearInterval(checkReady);
      startKeepalive();
      startQrDetection();
      observer.observe(document.body, { childList: true, subtree: true });
      chrome.runtime.sendMessage({ type: "WHATSAPP_READY" });
    }
  }, 2000);
}

/* Notify background when page unloads */
window.addEventListener('beforeunload', function() {
  chrome.runtime.sendMessage({ type: "WHATSAPP_CLOSED" });
});

init();
