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
  var currentAudio = null;
  var micState = 'idle'; // idle | listening | thinking | speaking

  var MIC_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15a3.5 3.5 0 0 0 3.5-3.5v-5a3.5 3.5 0 0 0-7 0v5A3.5 3.5 0 0 0 12 15z"/><path d="M19 11.5a7 7 0 0 1-14 0"/><line x1="12" y1="18.5" x2="12" y2="22"/><line x1="8.5" y1="22" x2="15.5" y2="22"/></svg>';
  var STOP_SVG = '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="7" width="10" height="10" rx="2"/></svg>';
  var CHAT_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
  var SEND_SVG = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 11l18-8-8 18-2-8-8-2z"/></svg>';
  var CLOSE_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>';

  function el(tag, attrs, children) {
    var e = document.createElement(tag);
    attrs = attrs || {};
    for (var k in attrs) {
      if (k === 'style') e.style.cssText = attrs[k];
      else if (k === 'html') e.innerHTML = attrs[k];
      else if (k === 'class') e.className = attrs[k];
      else e.setAttribute(k, attrs[k]);
    }
    (children || []).forEach(function (c) { e.appendChild(c); });
    return e;
  }

  function hexToRgb(hex) {
    var m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex || '#c8fa3d');
    return m ? (parseInt(m[1], 16) + ',' + parseInt(m[2], 16) + ',' + parseInt(m[3], 16)) : '200,250,61';
  }

  function injectStyles(primary, theme) {
    var rgb = hexToRgb(primary);
    var isLight = theme === 'light';
    var panelBg = isLight ? '#ffffff' : '#14161c';
    var panelBg2 = isLight ? '#f4f5f7' : '#0e0f13';
    var textColor = isLight ? '#14161c' : '#f4f5f7';
    var borderColor = isLight ? '#e6e7eb' : '#23262e';
    var assistantBubbleBg = isLight ? '#eef0f3' : '#1a1d24';

    var css = `
      #recepta-widget-root { position: fixed; z-index: 999999; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
      #recepta-widget-root.br { right: 20px; bottom: 20px; }
      #recepta-widget-root.bl { left: 20px; bottom: 20px; }
      @media (max-width: 480px) { #recepta-widget-root.br, #recepta-widget-root.bl { right: 14px; left: 14px; bottom: 14px; } }

      .recepta-bubble { width: 62px; height: 62px; border-radius: 50%; background: ${primary}; box-shadow: 0 6px 24px rgba(0,0,0,.3); display: flex; align-items: center; justify-content: center; cursor: pointer; border: none; padding: 0; overflow: hidden; animation: recepta-bubble-pulse 2.6s infinite; }
      .recepta-bubble img { width: 100%; height: 100%; object-fit: cover; }
      .recepta-bubble svg { width: 26px; height: 26px; color: #0a0b0f; }
      @keyframes recepta-bubble-pulse { 0% { box-shadow: 0 0 0 0 rgba(${rgb},.5), 0 6px 24px rgba(0,0,0,.3); } 70% { box-shadow: 0 0 0 14px rgba(${rgb},0), 0 6px 24px rgba(0,0,0,.3); } 100% { box-shadow: 0 0 0 0 rgba(${rgb},0), 0 6px 24px rgba(0,0,0,.3); } }

      .recepta-panel { width: 370px; max-width: calc(100vw - 28px); height: 560px; max-height: calc(100vh - 110px); background: ${panelBg}; color: ${textColor}; border: 1px solid ${borderColor}; border-radius: 20px; display: none; flex-direction: column; overflow: hidden; box-shadow: 0 16px 56px rgba(0,0,0,.45); position: absolute; bottom: 78px; right: 0; }
      #recepta-widget-root.bl .recepta-panel { right: auto; left: 0; }
      .recepta-panel.open { display: flex; }

      .recepta-header { background: ${primary}; color: #0a0b0f; padding: 14px 16px; display:flex; justify-content:space-between; align-items:center; flex-shrink: 0; }
      .recepta-header-info { display: flex; align-items: center; gap: 10px; }
      .recepta-header-avatar { width: 30px; height: 30px; border-radius: 50%; overflow: hidden; background: rgba(10,11,15,.15); display:flex; align-items:center; justify-content:center; flex-shrink:0; }
      .recepta-header-avatar img { width: 100%; height: 100%; object-fit: cover; }
      .recepta-header-avatar svg { width: 16px; height: 16px; }
      .recepta-header-text { font-size: 13.5px; font-weight: 700; line-height: 1.25; }
      .recepta-header-sub { font-size: 10.5px; font-weight: 500; opacity: .75; }
      .recepta-close-btn { background: none; border: none; cursor: pointer; color: #0a0b0f; opacity: .7; padding: 4px; }
      .recepta-close-btn:hover { opacity: 1; }
      .recepta-close-btn svg { width: 18px; height: 18px; }

      .recepta-tabs { display: flex; border-bottom: 1px solid ${borderColor}; flex-shrink: 0; }
      .recepta-tab { flex: 1; text-align: center; padding: 11px 6px; font-size: 12.5px; font-weight: 600; color: ${isLight ? '#8a8f99' : '#5f636d'}; background: none; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px; border-bottom: 2px solid transparent; }
      .recepta-tab svg { width: 14px; height: 14px; }
      .recepta-tab.active { color: ${primary}; border-color: ${primary}; }

      .recepta-greeting { padding: 12px 16px; font-size: 12.5px; color: ${isLight ? '#5f636d' : '#9a9ea8'}; border-bottom: 1px solid ${borderColor}; flex-shrink: 0; }

      /* ---------- Voice view ---------- */
      .recepta-voice-view { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 18px; padding: 20px; overflow-y: auto; }
      .recepta-mic-circle { width: 108px; height: 108px; border-radius: 50%; background: ${primary}; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; color: #0a0b0f; position: relative; flex-shrink: 0; transition: transform .15s ease; }
      .recepta-mic-circle:active { transform: scale(.96); }
      .recepta-mic-circle svg { width: 40px; height: 40px; }
      .recepta-mic-circle.listening { background: #ff5a5a; color: #fff; animation: recepta-ring-red 1.4s infinite; }
      .recepta-mic-circle.speaking { animation: recepta-ring-primary 1.1s infinite; }
      .recepta-mic-circle.thinking { opacity: .55; cursor: default; }
      @keyframes recepta-ring-red { 0% { box-shadow: 0 0 0 0 rgba(255,90,90,.55); } 70% { box-shadow: 0 0 0 22px rgba(255,90,90,0); } 100% { box-shadow: 0 0 0 0 rgba(255,90,90,0); } }
      @keyframes recepta-ring-primary { 0% { box-shadow: 0 0 0 0 rgba(${rgb},.55); } 70% { box-shadow: 0 0 0 22px rgba(${rgb},0); } 100% { box-shadow: 0 0 0 0 rgba(${rgb},0); } }

      .recepta-voice-status { font-size: 13px; font-weight: 600; color: ${isLight ? '#5f636d' : '#9a9ea8'}; text-align: center; min-height: 18px; }
      .recepta-thinking-dots { display: inline-flex; gap: 3px; align-items: center; }
      .recepta-thinking-dots span { width: 5px; height: 5px; border-radius: 50%; background: currentColor; animation: recepta-dot-bounce 1.2s infinite ease-in-out; }
      .recepta-thinking-dots span:nth-child(2) { animation-delay: .15s; }
      .recepta-thinking-dots span:nth-child(3) { animation-delay: .3s; }
      @keyframes recepta-dot-bounce { 0%, 60%, 100% { transform: translateY(0); opacity: .4; } 30% { transform: translateY(-4px); opacity: 1; } }

      .recepta-voice-transcript { width: 100%; max-height: 190px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
      .recepta-voice-transcript .recepta-msg { max-width: 92%; font-size: 12.5px; }

      /* ---------- Chat view ---------- */
      .recepta-chat-view { flex: 1; display: none; flex-direction: column; overflow: hidden; }
      .recepta-messages { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; background: ${panelBg2}; }
      .recepta-msg { max-width: 82%; padding: 9px 13px; border-radius: 14px; font-size: 13px; line-height:1.45; word-wrap: break-word; }
      .recepta-msg.assistant { background: ${assistantBubbleBg}; color: ${textColor}; align-self: flex-start; border-top-left-radius:4px; }
      .recepta-msg.visitor { background: ${primary}; color:#0a0b0f; align-self: flex-end; border-top-right-radius:4px; }
      .recepta-typing-dots { display: inline-flex; gap: 4px; align-items: center; padding: 2px 0; }
      .recepta-typing-dots span { width: 6px; height: 6px; border-radius: 50%; background: ${isLight ? '#8a8f99' : '#7a7f89'}; animation: recepta-dot-bounce 1.2s infinite ease-in-out; }
      .recepta-typing-dots span:nth-child(2) { animation-delay: .15s; }
      .recepta-typing-dots span:nth-child(3) { animation-delay: .3s; }

      .recepta-input-row { display: flex; gap: 8px; padding: 12px; border-top: 1px solid ${borderColor}; background: ${panelBg}; flex-shrink: 0; }
      .recepta-input-row input { flex: 1; background: ${panelBg2}; border: 1px solid ${borderColor}; border-radius: 20px; padding: 10px 14px; color: ${textColor}; font-size: 13px; outline:none; }
      .recepta-send { width: 38px; height: 38px; border-radius: 50%; border: none; background: ${primary}; color:#0a0b0f; cursor:pointer; flex-shrink:0; display:flex; align-items:center; justify-content:center; }
      .recepta-send svg { width: 16px; height: 16px; }
      .recepta-powered { text-align: center; font-size: 10px; color: ${isLight ? '#b5b9c2' : '#42454d'}; padding: 6px 0 2px; }
    `;
    document.head.appendChild(el('style', { html: css }));
  }

  function scrollToBottom(container) { container.scrollTop = container.scrollHeight; }

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

  function boot() {
    fetch(ORIGIN + '/api/widget/config/' + AGENT_ID).then(function (r) {
      if (!r.ok) throw new Error('agent not available');
      return r.json();
    }).then(function (cfg) {
      config = cfg;
      render();
    }).catch(function () {
      console.warn('[Recepta] Agent not available or not published yet.');
    });
  }

  function render() {
    var widgetCfg = config.widget || {};
    var primary = widgetCfg.primary_color || '#c8fa3d';
    var theme = widgetCfg.theme || 'dark';
    injectStyles(primary, theme);

    var root = el('div', { id: 'recepta-widget-root', class: (widgetCfg.position === 'bottom-left' ? 'bl' : 'br') });

    // ---------- Launcher bubble ----------
    var bubbleInner = widgetCfg.avatar_url
      ? el('img', { src: widgetCfg.avatar_url, alt: config.name })
      : el('span', { html: CHAT_SVG });
    var bubble = el('button', { class: 'recepta-bubble', 'aria-label': 'Open chat' }, [bubbleInner]);

    // ---------- Header ----------
    var headerAvatar = el('div', { class: 'recepta-header-avatar' }, [
      widgetCfg.avatar_url ? el('img', { src: widgetCfg.avatar_url }) : el('span', { html: CHAT_SVG }),
    ]);
    var closeBtn = el('button', { class: 'recepta-close-btn', html: CLOSE_SVG });
    var header = el('div', { class: 'recepta-header' }, [
      el('div', { class: 'recepta-header-info' }, [
        headerAvatar,
        el('div', {}, [
          el('div', { class: 'recepta-header-text', html: config.name }),
          el('div', { class: 'recepta-header-sub', html: config.business_name }),
        ]),
      ]),
      closeBtn,
    ]);

    // ---------- Tabs ----------
    var talkTab = el('button', { class: 'recepta-tab active', html: MIC_SVG + '<span>Talk</span>' });
    var chatTab = el('button', { class: 'recepta-tab', html: CHAT_SVG + '<span>Type to chat</span>' });
    var tabs = el('div', { class: 'recepta-tabs' }, [talkTab, chatTab]);

    var greeting = el('div', { class: 'recepta-greeting', html: config.greeting_text || '' });

    // ---------- Voice view ----------
    var micCircle = el('button', { class: 'recepta-mic-circle', html: MIC_SVG, 'aria-label': 'Talk' });
    var voiceStatus = el('div', { class: 'recepta-voice-status', html: 'Tap to talk' });
    var voiceTranscript = el('div', { class: 'recepta-voice-transcript' });
    var voiceView = el('div', { class: 'recepta-voice-view' }, [micCircle, voiceStatus, voiceTranscript]);

    // ---------- Chat view ----------
    var messagesEl = el('div', { class: 'recepta-messages' });
    var chatInput = el('input', { type: 'text', placeholder: 'Type a message...' });
    var sendBtn = el('button', { class: 'recepta-send', html: SEND_SVG });
    var chatInputRow = el('div', { class: 'recepta-input-row' }, [chatInput, sendBtn]);
    var chatView = el('div', { class: 'recepta-chat-view' }, [messagesEl, chatInputRow]);

    var powered = el('div', { class: 'recepta-powered', html: 'Powered by Recepta' });

    var panel = el('div', { class: 'recepta-panel' }, [header, tabs, greeting, voiceView, chatView, powered]);

    root.appendChild(panel);
    root.appendChild(bubble);
    document.body.appendChild(root);

    // ---------- Interactions ----------
    bubble.addEventListener('click', function () { panel.classList.toggle('open'); });
    closeBtn.addEventListener('click', function () { panel.classList.remove('open'); });

    function activateTab(name) {
      var isVoice = name === 'voice';
      talkTab.classList.toggle('active', isVoice);
      chatTab.classList.toggle('active', !isVoice);
      voiceView.style.display = isVoice ? 'flex' : 'none';
      chatView.style.display = isVoice ? 'none' : 'flex';
    }
    talkTab.addEventListener('click', function () { activateTab('voice'); });
    chatTab.addEventListener('click', function () { activateTab('chat'); });
    activateTab('voice');

    // ---- Chat ----
    function addChatMessage(role, text) {
      messagesEl.appendChild(el('div', { class: 'recepta-msg ' + role, html: escapeHtml(text) }));
      scrollToBottom(messagesEl);
    }
    function showTypingIndicator() {
      var typing = el('div', { class: 'recepta-msg assistant', id: 'recepta-typing' }, [
        el('div', { class: 'recepta-typing-dots' }, [el('span'), el('span'), el('span')]),
      ]);
      messagesEl.appendChild(typing);
      scrollToBottom(messagesEl);
      return typing;
    }
    function removeTypingIndicator(node) { if (node && node.parentNode) node.parentNode.removeChild(node); }

    async function sendChat(text) {
      addChatMessage('visitor', text);
      if (!conversationId) await initSession('chat');
      var typingNode = showTypingIndicator();
      try {
        var res = await fetch(ORIGIN + '/api/widget/chat', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ agent_id: AGENT_ID, conversation_id: conversationId, message: text })
        });
        var data = await res.json();
        removeTypingIndicator(typingNode);
        addChatMessage('assistant', data.reply || "Sorry, I'm having trouble responding right now.");
      } catch (e) {
        removeTypingIndicator(typingNode);
        addChatMessage('assistant', "Sorry, I couldn't reach the server. Please try again.");
      }
    }
    sendBtn.addEventListener('click', function () {
      var text = chatInput.value.trim();
      if (!text) return;
      chatInput.value = '';
      sendChat(text);
    });
    chatInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') sendBtn.click(); });

    // ---- Voice ----
    function setMicState(state) {
      micState = state;
      micCircle.classList.remove('listening', 'speaking', 'thinking');
      if (state === 'listening') {
        micCircle.classList.add('listening');
        micCircle.innerHTML = STOP_SVG;
        voiceStatus.innerHTML = 'Listening... tap to stop';
      } else if (state === 'thinking') {
        micCircle.classList.add('thinking');
        micCircle.innerHTML = MIC_SVG;
        voiceStatus.innerHTML = '<span class="recepta-thinking-dots"><span></span><span></span><span></span></span> Thinking';
      } else if (state === 'speaking') {
        micCircle.classList.add('speaking');
        micCircle.innerHTML = MIC_SVG;
        voiceStatus.innerHTML = 'Speaking...';
      } else {
        micCircle.innerHTML = MIC_SVG;
        voiceStatus.innerHTML = 'Tap to talk';
      }
    }

    function addVoiceLine(role, text) {
      voiceTranscript.appendChild(el('div', { class: 'recepta-msg ' + role, html: escapeHtml(text) }));
      scrollToBottom(voiceTranscript);
    }

    async function sendVoice(blob) {
      setMicState('thinking');
      if (!conversationId) await initSession('voice');
      var fd = new FormData();
      fd.append('agent_id', AGENT_ID);
      fd.append('conversation_id', conversationId);
      fd.append('audio', blob, 'audio.webm');
      try {
        var res = await fetch(ORIGIN + '/api/widget/voice', { method: 'POST', body: fd });
        var data = await res.json();
        if (data.transcript) addVoiceLine('visitor', data.transcript);
        addVoiceLine('assistant', data.reply || "Sorry, I couldn't hear that clearly.");
        if (data.audio_base64) {
          setMicState('speaking');
          currentAudio = new Audio('data:audio/mpeg;base64,' + data.audio_base64);
          currentAudio.onended = function () { setMicState('idle'); };
          currentAudio.onerror = function () { setMicState('idle'); };
          currentAudio.play().catch(function () { setMicState('idle'); });
        } else {
          setMicState('idle');
        }
      } catch (e) {
        addVoiceLine('assistant', "Sorry, I couldn't reach the server. Please try again.");
        setMicState('idle');
      }
    }

    micCircle.addEventListener('click', async function () {
      if (micState === 'thinking') return;
      if (micState === 'speaking') {
        if (currentAudio) { currentAudio.pause(); currentAudio = null; }
        setMicState('idle');
        return;
      }
      if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
        return;
      }
      try {
        var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];
        mediaRecorder.ondataavailable = function (e) { audioChunks.push(e.data); };
        mediaRecorder.onstop = function () {
          var blob = new Blob(audioChunks, { type: 'audio/webm' });
          stream.getTracks().forEach(function (t) { t.stop(); });
          sendVoice(blob);
        };
        mediaRecorder.start();
        setMicState('listening');
      } catch (e) {
        voiceStatus.textContent = 'Microphone access is needed for voice chat.';
      }
    });

    // ---------- Auto-open with greeting after configured delay ----------
    var delay = (widgetCfg.delay_seconds || 6) * 1000;
    setTimeout(function () {
      panel.classList.add('open');
    }, delay);
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();