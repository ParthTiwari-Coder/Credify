// ===============================
// MV3 SERVICE WORKER (LOGIC ONLY)
// ===============================

const CONFIG = {
  API_BASE_URL: 'http://localhost:8000'
};

const state = new Map(); // tabId -> { tabId, options, sessionId, entries, startTime }

// -------------------------------
// Install defaults
// -------------------------------
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({
    settings: {
      targetLanguage: 'en',
      enableTranslation: false,
      ocrEnabled: true,
      audioEnabled: true
    }
  });
});

// -------------------------------
// Messaging router
// -------------------------------
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    switch (msg.type) {
      case 'START_PIPELINE':
        return await startPipeline(msg.tabId || sender.tab?.id, msg.payload);

      case 'STOP_PIPELINE':
        return await stopPipeline(msg.tabId || sender.tab?.id);

      case 'AUDIO_CHUNK':
        await sendToBackend(msg.payload, msg.tabId);
        return { success: true };

      case 'PING_STATE':
        return { active: state.has(sender.tab?.id) };

      case 'CAPTURE_VISIBLE_TAB':
        try {
          const dataUrl = await new Promise((resolve) => {
            chrome.tabs.captureVisibleTab(null, { format: 'jpeg', quality: 80 }, (dataUrl) => {
              if (chrome.runtime.lastError) {
                console.error('Capture failed', chrome.runtime.lastError);
                resolve(null);
              } else {
                resolve(dataUrl);
              }
            });
          });
          return { dataUrl };
        } catch (err) {
          console.error('Capture error', err);
          return { error: 'capture_failed' };
        }

      default:
        return { error: 'unknown_message' };
    }
  })().then(sendResponse);

  return true; // async
});

// -------------------------------
// Start pipeline
// -------------------------------
async function startPipeline(tabId, options = {}) {
  if (!tabId) {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    tabId = tab?.id;
  }
  if (!tabId) return { error: 'no_tab' };

  // If already running, stop it first to clear streams
  if (state.has(tabId)) {
    await stopPipeline(tabId);
    // Give it a moment to cleanup
    await new Promise(r => setTimeout(r, 500));
  }

  // Initialize Session State
  state.set(tabId, {
    tabId,
    sessionId: `session_${Date.now()}`,
    startTime: new Date().toISOString(),
    entries: [],
    options: {
      targetLanguage: options.targetLanguage || 'en',
      enableTranslation: !!options.enableTranslation,
      audioEnabled: !!options.audioEnabled,
      ocrEnabled: !!options.ocrEnabled
    }
  });

  // Start audio via offscreen document
  if (options.audioEnabled) {
    try {
      await ensureOffscreen();
      const streamId = await new Promise((resolve, reject) => {
        chrome.tabCapture.getMediaStreamId({ targetTabId: tabId }, (streamId) => {
          if (chrome.runtime.lastError) {
            reject(chrome.runtime.lastError);
          } else {
            resolve(streamId);
          }
        });
      });
      chrome.runtime.sendMessage({ type: 'START_AUDIO', tabId, streamId });
    } catch (err) {
      console.error('offscreen error', err);
      return { error: err?.message || 'offscreen_failed' };
    }
  }

  console.log(`Pipeline started for tab ${tabId}, Session: ${state.get(tabId).sessionId}`);

  safeSend(tabId, {
    type: 'PIPELINE_STARTED',
    payload: state.get(tabId).options
  });

  // Save initial session
  await autoSaveToBackend(tabId);

  return { success: true };
}

// -------------------------------
// Stop pipeline
// -------------------------------
async function stopPipeline(tabId) {
  // Always try to stop audio just in case
  chrome.runtime.sendMessage({ type: 'STOP_AUDIO', tabId });

  let sessionId = null;
  if (state.has(tabId)) {
    const session = state.get(tabId);
    sessionId = session.sessionId;

    // Final Save with trigger=true
    await autoSaveToBackend(tabId, true);

    state.delete(tabId);
  }

  // Notify Content Script (UI purposes only now)
  safeSend(tabId, { type: 'PIPELINE_STOPPED' });

  return { stopped: true, sessionId };
}

// -------------------------------
// Ensure offscreen document
// -------------------------------
async function ensureOffscreen() {
  if (!chrome.offscreen) throw new Error('offscreen_unavailable');
  const exists = await chrome.offscreen.hasDocument();
  console.log('Ensure offscreen doc: exists=', exists);
  if (!exists) {
    await chrome.offscreen.createDocument({
      url: 'offscreen.html',
      reasons: ['USER_MEDIA'],
      justification: 'Tab audio capture for subtitles'
    });
  }
}

// -------------------------------
// Send audio to backend
// -------------------------------
async function sendToBackend(base64Audio, tabId) {
  if (!tabId || !state.has(tabId)) {
    console.error('sendToBackend ignored: invalid tab or session ended');
    return;
  }

  try {
    const res = await fetch(`${CONFIG.API_BASE_URL}/api/speech-to-text`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        audio: base64Audio,
        source: 'tab_audio'
      })
    });

    if (!res.ok) throw new Error(res.status);
    const data = await res.json();

    if (data.original_text || data.translated_text) {
      console.log('Got STT data, saving...', data.original_text?.substring(0, 20));

      // Update State
      const session = state.get(tabId);
      const entry = {
        id: `sub_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
        timestamp_created: new Date().toISOString(),
        source: 'audio',
        language: data.detected_language || 'unknown',
        text: data.translated_text || data.original_text || '',
        original_text: data.original_text || '',
        confidence: data.confidence || 0.0,
        timestamp_start: data.timestamp
      };

      session.entries.push(entry);
      state.set(tabId, session);

      // Save to Backend Directly
      await autoSaveToBackend(tabId);

      // Send to UI (Optional now)
      safeSend(tabId, { type: 'AUDIO_SUBTITLE', payload: data });
    }

  } catch (err) {
    console.error('STT failed', err);
  }
}

// -------------------------------
// Auto Save Logic
// -------------------------------
async function autoSaveToBackend(tabId, triggerPipeline = false) {
  if (!state.has(tabId)) return;
  const session = state.get(tabId);

  const sessionData = {
    session_id: session.sessionId,
    type: "combined_session",
    start_time: session.startTime,
    entries: session.entries,
    last_updated: new Date().toISOString()
  };

  try {
    const response = await fetch(`${CONFIG.API_BASE_URL}/api/save-session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_data: sessionData,
        session_id: session.sessionId,
        trigger_pipeline: triggerPipeline
      })
    });

    if (response.ok) {
      console.log(`[Background] Saved session ${session.sessionId} (${session.entries.length} entries)`);
    } else {
      console.error('[Background] Save failed', response.status);
    }
  } catch (err) {
    console.error('[Background] Save error', err);
  }
}

// -------------------------------
// Safe tab messaging
// -------------------------------
function safeSend(tabId, msg) {
  chrome.tabs.sendMessage(tabId, msg, () => {
    if (chrome.runtime.lastError) {
      console.warn('safeSend failed:', chrome.runtime.lastError.message);
    }
  });
}

// -------------------------------
// Cleanup on tab close
// -------------------------------
chrome.tabs.onRemoved.addListener((tabId) => {
  if (state.has(tabId)) {
    stopPipeline(tabId);
  }
});
