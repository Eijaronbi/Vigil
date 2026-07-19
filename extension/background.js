let ws = null;
let isSpeaking = false;
let reconnectTimer = null;
let pingInterval = null;
let waConnected = false;
let authToken = "";

const RECONNECT_DELAY = 5000;
const PING_INTERVAL = 25000;

function getBackend() {
  return localStorage.getItem("vigil_backend") || "http://localhost:8002";
}

function getWSUrl() {
  const b = getBackend().replace(/^http/, "ws");
  return b + "/ws";
}

function authHeaders() {
  return authToken ? {"Authorization": "Bearer " + authToken, "Content-Type": "application/json"} : {"Content-Type": "application/json"};
}

function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  try {
    ws = new WebSocket(getWSUrl());
    ws.onopen = function() {
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
      startWsPing();
      chrome.action.setBadgeText({ text: "ON" });
      chrome.action.setBadgeBackgroundColor({ color: "#00FF41" });
    };
    ws.onmessage = function(event) {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "alert" && data.summary && !isSpeaking) {
          speakNow(data.summary, false);
        }
        if (data.type === "priority_alert") {
          speakNow(data.summary || ("Priority message from " + data.sender), true);
        }
      } catch (e) {}
    };
    ws.onclose = function() {
      ws = null;
      stopWsPing();
      chrome.action.setBadgeText({ text: "OFF" });
      chrome.action.setBadgeBackgroundColor({ color: "#FF4444" });
      scheduleReconnect();
    };
    ws.onerror = function() { if (ws) ws.close(); };
  } catch (e) {
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connectWebSocket, RECONNECT_DELAY);
}

function startWsPing() {
  stopWsPing();
  pingInterval = setInterval(function() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.send('{"type":"ping"}'); } catch(e) {}
    }
  }, PING_INTERVAL);
}

function stopWsPing() {
  if (pingInterval) { clearInterval(pingInterval); pingInterval = null; }
}

function speakNow(text, force) {
  if (!text) return;
  if (force) { window.speechSynthesis.cancel(); isSpeaking = false; }
  if (isSpeaking) return;
  isSpeaking = true;
  var utter = new SpeechSynthesisUtterance(text);
  utter.onend = function () { isSpeaking = false; };
  utter.onerror = function () { isSpeaking = false; };
  window.speechSynthesis.speak(utter);
}

chrome.alarms.create("vigil-keepalive", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(function(alarm) {
  if (alarm.name === "vigil-keepalive") {
    if (!ws || ws.readyState !== WebSocket.OPEN) connectWebSocket();
  }
});

chrome.runtime.onStartup.addListener(function() { connectWebSocket(); });
chrome.runtime.onInstalled.addListener(function() { connectWebSocket(); });

chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
  if (request.type === "NEW_MESSAGES") {
    for (var i = 0; i < request.messages.length; i++) {
      fetch(getBackend() + "/api/sources/whatsapp/message", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(request.messages[i]),
      }).catch(function (err) { console.error("Vigil: POST error", err); });
    }
    sendResponse({ success: true });
  } else if (request.type === "WHATSAPP_READY") {
    waConnected = true;
    chrome.action.setBadgeText({ text: "WA" });
    chrome.action.setBadgeBackgroundColor({ color: "#00FF41" });
    sendResponse({ success: true });
  } else if (request.type === "WHATSAPP_CLOSED") {
    waConnected = false;
    chrome.action.setBadgeText({ text: "OFF" });
    chrome.action.setBadgeBackgroundColor({ color: "#707070" });
    sendResponse({ success: true });
  } else if (request.type === "SESSION_EXPIRED") {
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icon.png",
      title: "Vigil — Session Expired",
      message: "WhatsApp Web session expired. Please scan the QR code to reconnect.",
      priority: 2
    });
    sendResponse({ success: true });
  } else if (request.type === "CHECK_MESSAGES") {
    fetch(getBackend() + "/api/messages?important=true&limit=5", {headers: authHeaders()})
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (Array.isArray(data) && data.length > 0 && !isSpeaking) {
          var text = data.map(function (m) { return m.summary || m.text; }).join(". ");
          speakNow(text, false);
        }
      })
      .catch(function (err) { console.error("Vigil: GET error", err); });
    sendResponse({ success: true });
  } else if (request.type === "SET_TOKEN") {
    authToken = request.token;
    sendResponse({ success: true });
  } else if (request.type === "SET_BACKEND") {
    localStorage.setItem("vigil_backend", request.url);
    connectWebSocket();
    sendResponse({ success: true });
  } else if (request.type === "GET_STATUS") {
    sendResponse({ connected: waConnected, wsConnected: !!(ws && ws.readyState === WebSocket.OPEN) });
  }
  return true;
});

try {
  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    var recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = "en-US";
    recognition.onresult = function (event) {
      var last = event.results[event.results.length - 1];
      var transcript = (last[0].transcript || "").toLowerCase().trim();
      if (transcript === "check messages" || transcript === "check message" || transcript === "check my messages") {
        chrome.runtime.sendMessage({ type: "CHECK_MESSAGES" });
      }
    };
    recognition.onerror = function () {
      setTimeout(function () { try { recognition.start(); } catch (_) {} }, 5000);
    };
    recognition.start();
  }
} catch (_) {}

connectWebSocket();
