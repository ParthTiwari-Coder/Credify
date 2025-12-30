// Subtitle overlay manager
class SubtitleOverlay {
  constructor() {
    this.container = null;
    this.activeSubtitles = new Map();
    this.nextId = 0;

    console.log('--- OVERLAY.JS CONSTRUCTOR ---');
    this.initialize();
  }

  /**
   * Initialize overlay container
   */
  initialize() {
    // Create overlay container
    this.container = document.createElement('div');
    this.container.id = 'ocr-subtitle-overlay';
    this.container.className = 'ocr-overlay-container';

    // Add to page
    this.mount();

    // Handle fullscreen changes
    document.addEventListener('fullscreenchange', () => this.mount());
    document.addEventListener('webkitfullscreenchange', () => this.mount());
  }

  /**
   * Mount overlay to appropriate container (body or fullscreen element)
   */
  mount() {
    const fsElement = document.fullscreenElement || document.webkitFullscreenElement;
    const target = fsElement || document.body;

    if (this.container && this.container.parentNode !== target) {
      target.appendChild(this.container);
    }
  }

  /**
   * Display subtitle on screen
   * @param {Object} ocrResult - OCR result object
   */
  showSubtitle(ocrResult) {
    console.log('Overlay showSubtitle called', ocrResult);
    // if (!ocrResult.original_text || ocrResult.original_text.length < CONFIG.MIN_TEXT_LENGTH) {
    //   return;
    // }

    const subtitleId = this.nextId++;

    // Create subtitle element
    const subtitleEl = document.createElement('div');
    subtitleEl.className = 'ocr-subtitle';
    subtitleEl.dataset.id = subtitleId;

    // Build subtitle content
    const textToShow = ocrResult.translated_text || ocrResult.original_text;

    subtitleEl.innerHTML = `
      <div class="subtitle-content">
        <div class="subtitle-text">${this.escapeHtml(textToShow)}</div>
        ${ocrResult.detected_language !== 'unknown' ?
        `<div class="subtitle-meta">
            <span class="language-badge">${ocrResult.detected_language.toUpperCase()}</span>
            ${ocrResult.confidence ?
          `<span class="confidence-badge">${Math.round(ocrResult.confidence * 100)}%</span>`
          : ''}
            ${ocrResult.timestamp ?
          `<span class="timestamp-badge">${ocrResult.timestamp}</span>`
          : ''}
          </div>`
        : ''}
      </div>
    `;

    // Add to container
    this.container.appendChild(subtitleEl);

    // Trigger animation
    requestAnimationFrame(() => {
      subtitleEl.classList.add('visible');
    });

    // Store reference
    this.activeSubtitles.set(subtitleId, {
      element: subtitleEl,
      timeout: null
    });

    // Auto-remove after duration
    const timeout = setTimeout(() => {
      this.hideSubtitle(subtitleId);
    }, CONFIG.SUBTITLE_DISPLAY_DURATION_MS);

    this.activeSubtitles.get(subtitleId).timeout = timeout;

    // Limit number of visible subtitles
    if (this.activeSubtitles.size > 3) {
      const firstId = this.activeSubtitles.keys().next().value;
      this.hideSubtitle(firstId);
    }
  }

  /**
   * Hide specific subtitle
   * @param {number} subtitleId - Subtitle ID to hide
   */
  hideSubtitle(subtitleId) {
    const subtitle = this.activeSubtitles.get(subtitleId);

    if (!subtitle) return;

    // Clear timeout
    if (subtitle.timeout) {
      clearTimeout(subtitle.timeout);
    }

    // Fade out
    subtitle.element.classList.remove('visible');

    // Remove from DOM after animation
    setTimeout(() => {
      if (subtitle.element && subtitle.element.parentNode) {
        subtitle.element.parentNode.removeChild(subtitle.element);
      }
      this.activeSubtitles.delete(subtitleId);
    }, CONFIG.SUBTITLE_FADE_DURATION_MS);
  }

  /**
   * Clear all subtitles
   */
  clearAll() {
    // Clear all timeouts
    for (const [id, subtitle] of this.activeSubtitles) {
      if (subtitle.timeout) {
        clearTimeout(subtitle.timeout);
      }

      if (subtitle.element && subtitle.element.parentNode) {
        subtitle.element.parentNode.removeChild(subtitle.element);
      }
    }

    this.activeSubtitles.clear();
  }

  /**
   * Show notification message
   * @param {string} message - Message to display
   * @param {string} type - Message type (info, success, error)
   */
  showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `ocr-notification ${type}`;
    notification.textContent = message;

    this.container.appendChild(notification);

    requestAnimationFrame(() => {
      notification.classList.add('visible');
    });

    setTimeout(() => {
      notification.classList.remove('visible');
      setTimeout(() => {
        if (notification.parentNode) {
          notification.parentNode.removeChild(notification);
        }
      }, 300);
    }, 3000);
  }

  /**
   * Escape HTML to prevent XSS
   * @param {string} text - Text to escape
   * @returns {string} Escaped text
   */
  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * Toggle overlay visibility
   * @param {boolean} visible - Show or hide overlay
   */
  setVisible(visible) {
    if (this.container) {
      this.container.style.display = visible ? 'block' : 'none';
    }
  }

  /**
   * Destroy overlay
   */
  destroy() {
    this.clearAll();

    if (this.container && this.container.parentNode) {
      this.container.parentNode.removeChild(this.container);
    }

    this.container = null;
  }

  /**
   * Get active subtitle count
   * @returns {number} Number of active subtitles
   */
  getActiveCount() {
    return this.activeSubtitles.size;
  }
  /**
   * Display pipeline verification result
   * @param {Object} result - Final pipeline result
   */
  showPipelineResult(result) {
    console.log('[Overlay] showPipelineResult called with:', result);
    if (!result || !result.claims) {
      console.warn('[Overlay] Result or claims missing');
      return;
    }

    try {
      // Remove existing container if any
      const existing = document.getElementById('fact-check-result-container');
      if (existing) existing.remove();

      // Create new container
      const resultContainer = document.createElement('div');
      resultContainer.id = 'fact-check-result-container';
      resultContainer.className = 'fact-check-result-container';

      // FORCE STYLES INLINE TO ENSURE VISIBILITY
      Object.assign(resultContainer.style, {
        position: 'fixed',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        width: '400px',
        maxHeight: '80vh',
        backgroundColor: 'rgba(16, 16, 16, 0.98)',
        zIndex: '2147483647',
        color: 'white',
        padding: '0',
        borderRadius: '12px',
        boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
        display: 'block',
        visibility: 'visible',
        opacity: '1',
        pointerEvents: 'auto',
        overflowY: 'auto'
      });

      // Count stats
      const total = result.total_claims;
      const trueClaims = result.claims.filter(c => c.verdict === 'True').length;
      const falseClaims = result.claims.filter(c => c.verdict === 'False').length;
      const misleadingClaims = result.claims.filter(c => c.verdict === 'Misleading').length;

      // Build HTML
      let html = `
        <div class="result-header" style="padding: 12px; background: rgba(255,255,255,0.1); display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #333;">
          <span class="result-title" style="font-weight: bold;">🛡️ Fact Check Complete</span>
          <button style="background:none; border:none; color:#aaa; font-size:20px; cursor:pointer;" onclick="document.getElementById('fact-check-result-container').remove()">×</button>
        </div>
        <div class="result-stats" style="display: flex; justify-content: space-around; padding: 10px; border-bottom: 1px solid #333;">
          <div style="text-align:center"><span style="display:block; font-weight:bold; font-size:16px;">${total}</span><span style="font-size:12px; color:#ccc;">Claims</span></div>
          <div style="text-align:center"><span style="display:block; font-weight:bold; font-size:16px; color:#ff5252;">${falseClaims}</span><span style="font-size:12px; color:#ccc;">False</span></div>
          <div style="text-align:center"><span style="display:block; font-weight:bold; font-size:16px; color:#ffb74d;">${misleadingClaims}</span><span style="font-size:12px; color:#ccc;">Misleading</span></div>
        </div>
        <div class="result-claims" style="padding: 10px;">
      `;

      result.claims.forEach(claim => {
        if (claim.verdict === 'True') return;

        const color = claim.verdict === 'False' ? '#ff5252' :
          claim.verdict === 'Misleading' ? '#ffb74d' : '#777';

        html += `
          <div style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #333;">
            <div style="font-style: italic; color: #ddd; margin-bottom: 4px;">"${claim.claim_text.substring(0, 80)}..."</div>
            <div style="display:inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; background-color: ${color}; color: black;">${claim.verdict}</div>
            <div style="font-size: 12px; color: #aaa; margin-top: 4px;">${claim.explanation?.substring(0, 100) || ''}...</div>
          </div>
        `;
      });

      html += `</div>`;
      resultContainer.innerHTML = html;

      // Append to BODY
      document.body.appendChild(resultContainer);
      console.log('[Overlay] Container appended to body');

    } catch (err) {
      console.error('[Overlay] Render error:', err);
    }
  }
}

// Make available globally
if (typeof window !== 'undefined') {
  window.SubtitleOverlay = SubtitleOverlay;
}