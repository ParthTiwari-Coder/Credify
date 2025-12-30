const API_BASE_URL = 'http://localhost:8000';

document.addEventListener('DOMContentLoaded', init);

async function init() {
    // 1. Get Session ID
    const sessionId = await getSessionId();
    if (!sessionId) {
        showError('No active session found.');
        return;
    }

    document.getElementById('session-info').textContent = `ID: ${sessionId}`;
    startPolling(sessionId);
}

function getSessionId() {
    return new Promise((resolve) => {
        chrome.storage.local.get(['current_session_id'], (result) => {
            resolve(result.current_session_id);
        });
    });
}

function startPolling(sessionId) {
    let attempts = 0;
    const maxAttempts = 30; // 60 seconds (2s interval)

    const poll = async () => {
        try {
            const res = await fetch(`${API_BASE_URL}/api/results/${sessionId}`);

            if (res.status === 404) {
                // Not ready, keep waiting
                if (attempts++ > maxAttempts) {
                    showError('Timed out waiting for results.');
                    return;
                }
                updateProgress(attempts);
                setTimeout(poll, 2000);
                return;
            }

            if (!res.ok) throw new Error('API Error');

            const result = await res.json();

            // If stage 5, we are done
            if (result.stage === 5) {
                renderResults(result);
            } else {
                // Still processing (intermediate stage)
                updateProgress(attempts, `Processing Stage ${result.stage}/5...`);
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

function updateProgress(attempts, text) {
    const el = document.getElementById('progress-text');
    if (text) el.textContent = text;
    else el.textContent = `Analyzing... (${attempts}s)`;
}

function renderResults(data) {
    document.getElementById('loading-state').classList.add('hidden');
    document.getElementById('results-content').classList.remove('hidden');

    // Stats
    const claims = data.claims || [];
    document.getElementById('total-claims').textContent = claims.length;
    document.getElementById('false-claims').textContent = claims.filter(c => c.verdict === 'False').length;
    document.getElementById('misleading-claims').textContent = claims.filter(c => c.verdict === 'Misleading').length;
    document.getElementById('verified-claims').textContent = claims.filter(c => c.verdict === 'True').length;

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

        let verdictClass = 'verdict-unverified';
        if (claim.verdict === 'False') verdictClass = 'verdict-false';
        if (claim.verdict === 'Misleading') verdictClass = 'verdict-misleading';
        if (claim.verdict === 'True') verdictClass = 'verdict-true';

        const sourcesHtml = claim.sources && claim.sources.length
            ? `<div class="source-list">Sources: ${claim.sources.map(s => `<span class="source-tag">${s}</span>`).join('')}</div>`
            : '';

        card.innerHTML = `
            <div class="claim-header">
                <blockquote class="claim-text">"${claim.claim}"</blockquote>
                <span class="verdict-badge ${verdictClass}">${claim.verdict}</span>
            </div>
            <div class="claim-explanation">
                ${claim.explanation || 'No explanation provided.'}
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
