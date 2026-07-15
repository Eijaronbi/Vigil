let lastMessageCount = 0;

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

const observer = new MutationObserver(() => {
  const messages = extractMessages();
  if (messages && messages.length > 0) {
    chrome.runtime.sendMessage({ type: "NEW_MESSAGES", messages });
  }
});

observer.observe(document.body, { childList: true, subtree: true });
