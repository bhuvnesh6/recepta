(function () {
  var scriptTag = document.currentScript || (function () {
    var scripts = document.getElementsByTagName('script');
    return scripts[scripts.length - 1];
  })();
  var AGENT_ID = scriptTag.getAttribute('data-agent-id');
  var ORIGIN = new URL(scriptTag.src).origin;
  if (!AGENT_ID) { console.error('[Recepta] Missing data-agent-id on widget script tag.'); return; }

  var STORAGE_KEY = 'recepta_visitor_id_' + AGENT_ID;
  var visitorId = localStorage.getItem(STORAGE_KEY) || null;
  var conversationId = null;
  var config = null;
  var mediaRecorder = null;
  var audioChunks = [];

  function el(tag, attrs, children) {
    var e = document.createElement(tag);
    attrs = attrs || {};
    for (var k in attrs) {
      if (k === 'style') e.style.cssText = attrs[k];
      else if (k === 'html') e.innerHTML = attrs[k];
      else e.setAttribute(k, attrs[k]);
    }
    (children || []).forEach(function (c) { e.appendChild(c); });
    return e;
  }

  function injectStyles(primary) {
    var css = `
      #recepta-widget-root { position: fixed; z-index: 999999; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
      #recepta-widget-root.br { right: 20px; bottom: 20px; }
      #recepta-widget-root.bl { left: 20px; bottom: 20px; }
      .recepta-bubble { width: 60px; height: 60px; border-radius: 50%; background: ${primary}; box-shadow: 0 6px 24px rgba(0,0,0,.25); display: flex; align-items: center; justify-content: center; cursor: pointer; border: none; }
      .recepta-panel { width: 360px; max-width: calc(100vw - 40px); height: 520px; max-height: calc(100vh - 100px); background: #14161c; border: 1px solid #23262e; border-radius: 18px; display: none; flex-direction: column; overflow: hidden; box-shadow: 0 12px 48px rgba(0,0,0,.4); position: absolute; bottom: 74px; right: 0; }
      #recepta-widget-root.bl .recepta-panel { right: auto; left: 0; }
      .recepta-panel.open { display: flex; }
      .recepta-header { background: ${primary}; color: #0a0b0f; padding: 14px 16px; font-weight: 700; font-size: 14px; display:flex; justify-content:space-between; align-items:center; }
      .recepta-messages { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; background:#0e0f13; }
      .recepta-msg { max-width: 82%; padding: 9px 13px; border-radius: 14px; font-size: 13px; line-height:1.4; color:#f4f5f7; }
      .recepta-msg.assistant { background: #1a1d24; align-self: flex-start; border-top-left-radius:4px; }
      .recepta-msg.visitor { background: ${primary}; color:#0a0b0f; align-self: flex-end; border-top-right-radius:4px; }
      .recepta-input-row { display: flex; gap: 8px; padding: 12px; border-top: 1px solid #23262e; background:#14161c; }
      .recepta-input-row input { flex: 1; background: #0e0f13; border: 1px solid #23262e; border-radius: 20px; padding: 9px 14px; color: #f4f5f7; font-size: 13px; outline:none; }
      .recepta-send, .recepta-mic { width: 36px; height: 36px; border-radius: 50%; border: none; background: ${primary}; color:#0a0b0f; font-weight:700; cursor:pointer; flex-shrink:0; }
      .recepta-mic.recording { background: #ff6b6b; color:#fff; }
      .recepta-close { cursor: pointer; font-size: 16px; }
    `;
    document.head.appendChild(el('style', { html: css }));
  }

  function addMessage(container, role, text) {
    container.appendChild(el('div', { class: 'recepta-msg ' + role, html: text }));
    container.scrollTop = container.scrollHeight;
  }

  async function initSession(channel) {
    var res = await fetch(ORIGIN + '/api/widget/session', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: AGENT_ID, channel: channel, visitor_id: visitorId })
    });
    var data = await res.json();
    visitorId = data.visitor_id;
    conversationId = data.conversation_id;
    localStorage.setItem(STORAGE_KEY, visitorId);
  }

  async function sendChat(text, messagesEl) {
    addMessage(messagesEl, 'visitor', text);
    if (!conversationId) await initSession('chat');
    var res = await fetch(ORIGIN + '/api/widget/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: AGENT_ID, conversation_id: conversationId, message: text })
    });
    var data = await res.json();
    addMessage(messagesEl, 'assistant', data.reply || "Sorry, I'm having trouble responding right now.");
  }

  async function sendVoice(blob, messagesEl) {
    if (!conversationId) await initSession('voice');
    var fd = new FormData();
    fd.append('agent_id', AGENT_ID);
    fd.append('conversation_id', conversationId);
    fd.append('audio', blob, 'audio.webm');
    addMessage(messagesEl, 'visitor', '🎙 (voice message)');
    var res = await fetch(ORIGIN + '/api/widget/voice', { method: 'POST', body: fd });
    var data = await res.json();
    if (data.transcript) messagesEl.lastChild.innerHTML = data.transcript;
    addMessage(messagesEl, 'assistant', data.reply || "Sorry, I couldn't hear that clearly.");
    if (data.audio_base64) {
      var audio = new Audio('data:audio/mpeg;base64,' + data.audio_base64);
      audio.play().catch(function () {});
    }
  }

  async function boot() {
    var res = await fetch(ORIGIN + '/api/widget/config/' + AGENT_ID);
    if (!res.ok) return;
    config = await res.json();
    var widgetCfg = config.widget || {};
    var primary = widgetCfg.primary_color || '#c8fa3d';
    injectStyles(primary);

    var root = el('div', { id: 'recepta-widget-root', class: (widgetCfg.position === 'bottom-left' ? 'bl' : 'br') });

    var messagesEl = el('div', { class: 'recepta-messages' });
    var input = el('input', { type: 'text', placeholder: 'Type a message...' });
    var sendBtn = el('button', { class: 'recepta-send', html: '➤' });
    var micBtn = el('button', { class: 'recepta-mic', html: '🎙' });

    var panel = el('div', { class: 'recepta-panel' }, [
      el('div', { class: 'recepta-header' }, [
        el('span', { html: config.name + ' · ' + config.business_name }),
        el('span', { class: 'recepta-close', html: '&times;' }),
      ]),
      messagesEl,
      el('div', { class: 'recepta-input-row' }, [input, micBtn, sendBtn]),
    ]);

    var bubble = el('button', { class: 'recepta-bubble', html: '💬' });

    bubble.addEventListener('click', function () {
      panel.classList.toggle('open');
    });
    panel.querySelector('.recepta-close').addEventListener('click', function () {
      panel.classList.remove('open');
    });

    sendBtn.addEventListener('click', function () {
      var text = input.value.trim();
      if (!text) return;
      input.value = '';
      sendChat(text, messagesEl);
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') sendBtn.click();
    });

    micBtn.addEventListener('click', async function () {
      if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
        micBtn.classList.remove('recording');
        return;
      }
      try {
        var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];
        mediaRecorder.ondataavailable = function (e) { audioChunks.push(e.data); };
        mediaRecorder.onstop = function () {
          var blob = new Blob(audioChunks, { type: 'audio/webm' });
          sendVoice(blob, messagesEl);
          stream.getTracks().forEach(function (t) { t.stop(); });
        };
        mediaRecorder.start();
        micBtn.classList.add('recording');
      } catch (e) {
        alert('Microphone access is needed for voice chat.');
      }
    });

    root.appendChild(panel);
    root.appendChild(bubble);
    document.body.appendChild(root);

    var delay = (widgetCfg.delay_seconds || 6) * 1000;
    setTimeout(function () {
      if (config.greeting_text) addMessage(messagesEl, 'assistant', config.greeting_text);
      panel.classList.add('open');
    }, delay);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
