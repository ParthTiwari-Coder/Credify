// ==============================
console.log('%c--- CONTENT.JS LOADING ---', 'color: green; font-size: 16px; font-weight: bold');
console.log('%cTrueLens Extension Active', 'color: blue; font-size: 14px');
// Local config (MV3 safe)
// ==============================
const LOCAL_CONFIG = {
  API_BASE_URL: 'http://localhost:8000',
  OCR_INTERVAL_MS: 1000  // Faster OCR updates (was 1500ms)
};

const api = new APIClient(LOCAL_CONFIG.API_BASE_URL);
const overlay = new SubtitleOverlay();
window.factCheckOverlay = overlay; // Expose for SessionManager
const sessionManager = new SessionManager();

let ocrTimer = null;
let options = {
  targetLanguage: 'en',
  enableTranslation: false,
  ocrEnabled: true,
  audioEnabled: true
};

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'PIPELINE_STARTED':
      options = { ...options, ...message.payload };
      sessionManager.resetSession(); // Start new session on pipeline start
      overlay.showNotification('Session Started', 'success');
      startOCRLoop();
      sendResponse?.({ success: true });
      return true;

    case 'PIPELINE_STOPPED':
      stopOCRLoop(true);
      const currentSessionId = sessionManager.sessionId;
      // Finalize session to ensure last bits are saved and result is displayed
      if (sessionManager.entries.length > 0) {
        sessionManager.finalizeSession();
        overlay.showNotification(`Session Stopped - ${sessionManager.entries.length} entries processed`, 'success');
      } else {
        overlay.showNotification('Session Stopped', 'info');
      }
      sendResponse?.({ success: true, sessionId: currentSessionId });
      return true;

    case 'AUDIO_SUBTITLE':
      console.log('Content script received AUDIO_SUBTITLE', message.payload);
      if (message.payload?.translated_text || message.payload?.original_text) {
        sessionManager.addEntry('subtitle', message.payload); // Store audio subtitle
        overlay.showSubtitle(message.payload);
      }
      return true;

    case 'TRIGGER_SCREEN_SEARCH':
      handleScreenSearch();
      return true;

    case 'SAVE_SELECTED_TEXT':
      handleSaveSelectedText();
      return true;
  }
});

async function handleScreenSearch() {
  overlay.showNotification('📸 Capturing screenshot...', 'info');
  try {
    // Request screenshot from background
    const response = await chrome.runtime.sendMessage({ type: 'CAPTURE_VISIBLE_TAB' });

    if (!response || !response.dataUrl) {
      throw new Error('Screenshot failed');
    }

    const imageData = response.dataUrl;
    const imageId = `img_${Date.now()}`;

    // Save image to backend first
    try {
      const saveImageResponse = await fetch('http://localhost:8000/api/save-image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_data: imageData,
          image_id: imageId,
          source: 'screen_capture'
        })
      });

      if (saveImageResponse.ok) {
        const imageResult = await saveImageResponse.json();
        console.log(`[Content] Image saved: ${imageResult.relative_path}`);
      }
    } catch (imgErr) {
      console.error('[Content] Image save failed:', imgErr);
      // Continue with OCR even if image save fails
    }

    overlay.showNotification('🔍 Extracting text...', 'info');

    // Process OCR
    const result = await api.processOCR(imageData, {
      targetLanguage: options.targetLanguage,
      enableTranslation: options.enableTranslation,
      timestamp: formatTimestamp(document.querySelector('video')?.currentTime || 0),
      source: 'screen_capture'
    });

    if (result && (result.original_text || result.translated_text)) {
      // Add image reference to result
      result.image_id = imageId;
      result.image_path = `sessions/images/${imageId}.jpg`;

      sessionManager.addEntry('screen_ocr', result);
      overlay.showSubtitle(result);

      // Count text regions if available
      const textCount = result.text_regions ? result.text_regions.length : 1;
      overlay.showNotification(`✅ Scan complete! Found ${textCount} text region(s)`, 'success');
    } else {
      overlay.showNotification('✅ Scan complete - No text found', 'info');
    }

  } catch (err) {
    console.error('Screen search failed:', err);
    overlay.showNotification('❌ Screen scan failed', 'error');
  }
}

async function handleExtractKeyframes() {
  overlay.showNotification('🎬 Extracting video keyframes...', 'info');
  try {
    const video = document.querySelector('video');
    if (!video) {
      overlay.showNotification('❌ No video found on this page', 'error');
      return;
    }

    if (video.readyState < 2) {
      overlay.showNotification('⏳ Waiting for video to load...', 'info');
      await new Promise((resolve) => {
        video.addEventListener('loadedmetadata', resolve, { once: true });
        setTimeout(resolve, 5000); // Timeout after 5 seconds
      });
    }

    const duration = video.duration;
    if (!duration || duration === 0) {
      overlay.showNotification('❌ Video duration not available', 'error');
      return;
    }

    overlay.showNotification(`📸 Extracting frames (every 3 seconds)...`, 'info');

    const keyframes = [];
    const interval = 3; // Extract 1 frame every 3 seconds
    const originalTime = video.currentTime;
    const originalPaused = video.paused;

    // Pause video for extraction
    if (!video.paused) {
      video.pause();
    }

    // Extract keyframes
    for (let time = 0; time < duration; time += interval) {
      try {
        video.currentTime = time;
        await new Promise((resolve) => {
          video.addEventListener('seeked', resolve, { once: true });
          setTimeout(resolve, 1000); // Timeout after 1 second
        });

        // Wait a bit for frame to render
        await new Promise(resolve => setTimeout(resolve, 100));

        // Capture frame
        const frameData = captureFrame(video);
        if (frameData) {
          const imageId = `keyframe_${Date.now()}_${Math.floor(time)}`;

          // Save image to backend
          try {
            const saveImageResponse = await fetch('http://localhost:8000/api/save-image', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                image_data: frameData,
                image_id: imageId,
                source: 'video_keyframe'
              })
            });

            if (saveImageResponse.ok) {
              const imageResult = await saveImageResponse.json();
              keyframes.push({
                image_id: imageId,
                image_path: imageResult.relative_path,
                timestamp: time,
                timestamp_formatted: formatTimestamp(time)
              });
              console.log(`[Content] Keyframe saved at ${time}s: ${imageId}`);
            }
          } catch (imgErr) {
            console.error('[Content] Keyframe save failed:', imgErr);
          }
        }
      } catch (err) {
        console.error(`[Content] Failed to extract frame at ${time}s:`, err);
      }
    }

    // Restore video state
    video.currentTime = originalTime;
    if (!originalPaused) {
      video.play();
    }

    // Add keyframes to session
    for (const keyframe of keyframes) {
      sessionManager.addEntry('screen_ocr', {
        image_id: keyframe.image_id,
        image_path: keyframe.image_path,
        text: `Video keyframe at ${keyframe.timestamp_formatted}`,
        source: 'video_keyframe',
        timestamp: keyframe.timestamp,
        confidence: 1.0
      });
    }

    overlay.showNotification(`✅ Extracted ${keyframes.length} keyframes`, 'success');
  } catch (err) {
    console.error('Keyframe extraction failed:', err);
    overlay.showNotification('❌ Keyframe extraction failed', 'error');
  }
}

function handleSaveSelectedText() {
  try {
    // Get selected text from page
    const selectedText = window.getSelection().toString().trim();

    if (!selectedText) {
      overlay.showNotification('No text selected', 'info');
      return;
    }

    // Get selection metadata
    const selection = window.getSelection();
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();

    // Create entry data
    const entryData = {
      original_text: selectedText,
      translated_text: selectedText,
      detected_language: 'unknown', // Could add language detection later
      confidence: 1.0,
      source: 'user_selection',
      timestamp: formatTimestamp(document.querySelector('video')?.currentTime || 0),
      selection_metadata: {
        page_url: window.location.href,
        page_title: document.title,
        position: {
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: Math.round(rect.width),
          height: Math.round(rect.height)
        }
      }
    };

    // Save to session
    sessionManager.addEntry('selected_text', entryData);

    // Show notification
    overlay.showNotification(`Saved: "${selectedText.substring(0, 30)}${selectedText.length > 30 ? '...' : ''}"`, 'success');

    console.log('[Content] Saved selected text:', selectedText);
  } catch (err) {
    console.error('Save selected text failed:', err);
    overlay.showNotification('Failed to save selected text', 'error');
  }
}

function startOCRLoop() {
  if (ocrTimer || !options.ocrEnabled) return;

  ocrTimer = setInterval(async () => {
    const video = document.querySelector('video');
    if (!video || video.paused || video.readyState < 2) return;

    const frame = window.captureFrame?.(video);
    if (!frame) return;

    try {
      const result = await api.processOCR(frame, {
        targetLanguage: options.targetLanguage,
        enableTranslation: options.enableTranslation,
        timestamp: formatTimestamp(video.currentTime),
        source: 'video_frame'
      });

      if (result && isNewContent(result.translated_text || result.original_text)) {
        sessionManager.addEntry('subtitle', result); // Store video subtitle
        overlay.showSubtitle(result);
      }
    } catch (err) {
    }
  }, LOCAL_CONFIG.OCR_INTERVAL_MS);
}

function stopOCRLoop(clearOverlay = false) {
  if (ocrTimer) {
    clearInterval(ocrTimer);
    ocrTimer = null;
  }
  // Don't clear overlay immediately on stop, maybe user wants to read last subtitle
  if (clearOverlay) overlay.clearAll();
}

function formatTimestamp(seconds) {
  const hrs = String(Math.floor(seconds / 3600)).padStart(2, '0');
  const mins = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0');
  const secs = String(Math.floor(seconds % 60)).padStart(2, '0');
  return `${hrs}:${mins}:${secs}`;
}

