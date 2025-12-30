const langSelect = document.getElementById('langSelect');
const translateToggle = document.getElementById('translateToggle');
const audioToggle = document.getElementById('audioToggle');
const ocrToggle = document.getElementById('ocrToggle');
const statusEl = document.getElementById('status');
const settingsBtn = document.getElementById('settingsBtn');
const settingsPanel = document.getElementById('settingsPanel');
const stopBtn = document.getElementById('stopBtn');

let isRunning = false;

init();

async function init() {
  populateLanguages();

  // Settings toggle
  settingsBtn.addEventListener('click', () => {
    const isVisible = settingsPanel.style.display !== 'none';
    settingsPanel.style.display = isVisible ? 'none' : 'block';
  });

  // Button listeners
  document.getElementById('startBtn').addEventListener('click', onStart);
  document.getElementById('stopBtn').addEventListener('click', onStop);
  document.getElementById('searchScreenBtn').addEventListener('click', onSearchScreen);
  document.getElementById('saveSelectedBtn').addEventListener('click', onSaveSelected);
  document.getElementById('extractKeyframesBtn').addEventListener('click', onExtractKeyframes);
  document.getElementById('backBtn').addEventListener('click', showMain);
}

async function populateLanguages() {
  const fallback = CONFIG.SUPPORTED_LANGUAGES;
  try {
    const res = await fetch(`${CONFIG.API_BASE_URL}/api/languages`);
    if (!res.ok) throw new Error('lang_fetch_fail');
    const languages = await res.json();
    languages.forEach((lang) => addLangOption(lang.code, lang.name));
  } catch (err) {
    Object.entries(fallback).forEach(([code, name]) => addLangOption(code, name));
  }
}

function addLangOption(code, name) {
  const opt = document.createElement('option');
  opt.value = code;
  opt.textContent = `${name} (${code})`;
  langSelect.appendChild(opt);
}

async function onStart() {
  const options = {
    targetLanguage: langSelect.value || 'en',
    enableTranslation: translateToggle.checked,
    audioEnabled: audioToggle.checked,
    ocrEnabled: ocrToggle.checked
  };

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    setStatus('Error: no active tab', 'error');
    return;
  }

  setStatus('Starting analysis...', 'active');
  const res = await chrome.runtime.sendMessage({ type: 'START_PIPELINE', tabId: tab.id, payload: options });
  if (res?.success) {
    isRunning = true;
    setStatus('✓ Analysis running (click Finish to verify)', 'active');
  } else {
    setStatus(`Error: ${res?.error || 'unknown'}`, 'error');
  }
}

async function onStop() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const res = await chrome.runtime.sendMessage({ type: 'STOP_PIPELINE', tabId: tab?.id });
  isRunning = false;
  setStatus(res?.stopped ? 'Validation triggered' : 'Stop failed', res?.stopped ? '' : 'error');

  // Open Results View
  if (res?.stopped) {
    if (res.sessionId) {
      console.log('Using returned session ID:', res.sessionId);
      showResults(res.sessionId);
    } else {
      // Fallback
      chrome.storage.local.get(['current_session_id'], (data) => {
        if (data.current_session_id) {
          showResults(data.current_session_id);
        }
      });
    }
  }
}

// VIEW SWITCHING
function showResults(sessionId) {
  document.getElementById('main-view').classList.add('hidden');
  document.getElementById('results-view').classList.remove('hidden');
  startPolling(sessionId);
}

function showMain() {
  document.getElementById('results-view').classList.add('hidden');
  document.getElementById('main-view').classList.remove('hidden');
}

// POLLING LOGIC
function startPolling(sessionId) {
  let attempts = 0;
  const maxAttempts = 150; // 5 minutes (2s interval)

  // Reset UI
  document.getElementById('loading-state').classList.remove('hidden');
  document.getElementById('error-state').classList.add('hidden');
  document.getElementById('report-content').classList.add('hidden');
  document.getElementById('progress-text').textContent = 'Initializing...';

  const poll = async () => {
    try {
      const res = await fetch(`${CONFIG.API_BASE_URL}/api/results/${sessionId}`);

      if (res.status === 404) {
        if (attempts++ > maxAttempts) {
          showError('Timed out waiting for results.');
          return;
        }
        document.getElementById('progress-text').textContent = `Analyzing... (${attempts}s)`;
        setTimeout(poll, 2000);
        return;
      }

      if (!res.ok) throw new Error('API Error');

      const result = await res.json();

      if (result.stage === 5) {
        renderResults(result);
      } else {
        document.getElementById('progress-text').textContent = `Processing Stage ${result.stage}/5...`;
        setTimeout(poll, 1500);
      }

    } catch (err) {
      console.error(err);
      if (attempts++ > maxAttempts) {
        showError('Connection failed.');
      } else {
        setTimeout(poll, 2000);
      }
    }
  };

  poll();
}

function renderResults(data) {
  document.getElementById('loading-state').classList.add('hidden');
  document.getElementById('report-content').classList.remove('hidden');

  const claims = data.claims || [];

  // Stats - Normalize to uppercase for comparison
  document.getElementById('total-claims').textContent = claims.length;
  document.getElementById('false-claims').textContent = claims.filter(c => c.verdict?.toUpperCase() === 'FALSE').length;
  document.getElementById('verified-claims').textContent = claims.filter(c => c.verdict?.toUpperCase() === 'TRUE').length;

  // List
  const list = document.getElementById('claims-list');
  list.innerHTML = '';

  if (claims.length === 0) {
    list.innerHTML = '<div class="center-content">No verifiable claims found.</div>';
    return;
  }

  claims.forEach(claim => {
    const card = document.createElement('div');
    card.className = 'claim-card';

    const verdict = claim.verdict ? claim.verdict.toUpperCase() : 'UNVERIFIED';

    let verdictClass = 'verdict-unverified';
    if (verdict === 'FALSE') verdictClass = 'verdict-false';
    if (verdict === 'MISLEADING') verdictClass = 'verdict-misleading';
    if (verdict === 'TRUE') verdictClass = 'verdict-true';

    const sourcesHtml = claim.sources && claim.sources.length
      ? `<div class="source-list">Sources: ${claim.sources.map(s => `<span class="source-tag">${s}</span>`).join('')}</div>`
      : '';

    card.innerHTML = `
          <div class="claim-header">
              <blockquote class="claim-text">"${claim.claim}"</blockquote>
              <span class="verdict-badge ${verdictClass}">${verdict}</span>
          </div>
          <div class="claim-explanation">
              ${claim.explanation || claim.verification_reasoning || 'No explanation provided.'}
              ${sourcesHtml}
          </div>
      `;
    list.appendChild(card);
  });
}

function showError(msg) {
  document.getElementById('loading-state').classList.add('hidden');
  document.getElementById('error-state').classList.remove('hidden');
  document.getElementById('error-message').textContent = msg;
}

async function onSearchScreen() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id) {
    setStatus('🎥 Searching screen...', 'active');

    // Retry logic
    let attempts = 0;
    const maxAttempts = 3;

    while (attempts < maxAttempts) {
      try {
        await chrome.tabs.sendMessage(tab.id, { type: 'TRIGGER_SCREEN_SEARCH' });
        setStatus('✓ Screen search triggered', 'active');
        return;
      } catch (err) {
        attempts++;
        if (attempts < maxAttempts) {
          await new Promise(resolve => setTimeout(resolve, 100));
        } else {
          setStatus('Error: Refresh page and try again', 'error');
        }
      }
    }
  } else {
    setStatus('Error: no active tab', 'error');
  }
}

async function onSaveSelected() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id) {
    // Check if on a valid webpage
    if (tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://')) {
      setStatus('Error: Navigate to a webpage first', 'error');
      return;
    }

    setStatus('💾 Saving selected text...', 'active');

    // Retry logic
    let attempts = 0;
    while (attempts < 3) {
      try {
        await chrome.tabs.sendMessage(tab.id, { type: 'SAVE_SELECTED_TEXT' });
        setStatus('✓ Selected text saved', 'active');
        return;
      } catch (err) {
        attempts++;
        if (attempts < 3) {
          await new Promise(r => setTimeout(r, 100));
        } else {
          setStatus('Error: Refresh page and try again', 'error');
        }
      }
    }
  } else {
    setStatus('Error: no active tab', 'error');
  }
}

async function onExtractKeyframes() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id) {
    // Check if on a valid webpage
    if (tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://')) {
      setStatus('Error: Navigate to a webpage first', 'error');
      return;
    }

    setStatus('🎬 Extracting keyframes...', 'active');

    // Retry logic
    let attempts = 0;
    while (attempts < 3) {
      try {
        await chrome.tabs.sendMessage(tab.id, { type: 'EXTRACT_KEYFRAMES' });
        setStatus('✓ Keyframe extraction started', 'active');
        return;
      } catch (err) {
        attempts++;
        if (attempts < 3) {
          await new Promise(r => setTimeout(r, 100));
        } else {
          setStatus('Error: Refresh page and try again', 'error');
        }
      }
    }
  } else {
    setStatus('Error: no active tab', 'error');
  }
}

// Helper function to set status with CSS classes
function setStatus(message, type = '') {
  statusEl.textContent = message;
  statusEl.className = 'status';
  if (type) {
    statusEl.classList.add(type);
  }
}
