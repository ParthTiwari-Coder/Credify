/**
 * Manages session storage for subtitles and OCR results.
 * Automatically saves data to chrome.storage.local on every entry.
 */
class SessionManager {
    constructor() {
        this.sessionId = `session_${Date.now()}`;
        this.startTime = new Date().toISOString();
        this.entries = [];
        this.autoSaveEnabled = true;
        console.log(`SessionManager initialized: ${this.sessionId}`);
    }

    /**
     * Add a new entry to the session
     * @param {string} type - 'subtitle' or 'screen_ocr'
     * @param {Object} data - The data object to store
     */
    addEntry(type, data) {
        const baseTimestamp = new Date().toISOString();
        const baseId = Date.now();

        // Handle Screen OCR with multiple regions
        if (type === 'screen_ocr' && data.text_regions && data.text_regions.length > 0) {
            const imageId = data.image_id || `img_${baseId}`;

            data.text_regions.forEach((region, index) => {
                const entry = {
                    id: `img_txt_${baseId}_${index}`,
                    timestamp_created: baseTimestamp,
                    source: 'image', // Requirement: source "image"
                    image_id: imageId,
                    language: data.detected_language || 'unknown',
                    text: region.text,
                    confidence: region.confidence || 0.0,
                    bbox: region.bbox
                };
                this.entries.push(entry);
            });
            console.log(`[SessionManager] Added ${data.text_regions.length} OCR regions from ${imageId}`);
            this.autoSave(); // Auto-save after adding entries
            return;
        }

        // Fallback or Standard Subtitle
        const entryId = `${type === 'subtitle' ? 'sub' : type === 'selected_text' ? 'sel' : 'img_txt'}_${baseId}_${Math.floor(Math.random() * 1000)}`;

        const entry = {
            id: entryId,
            timestamp_created: baseTimestamp,
            source: type === 'subtitle' ? (data.source || 'audio') :
                type === 'selected_text' ? 'user_selection' : 'image',
            language: data.detected_language || 'unknown',
            text: data.translated_text || data.original_text || '',
            original_text: data.original_text || '',
            confidence: data.confidence || 0.0
        };

        if (type === 'subtitle') {
            entry.timestamp_start = data.timestamp || null;
        } else if (type === 'screen_ocr') {
            entry.image_id = data.image_id || `img_${baseId}`;
            entry.bbox = data.bbox || [];
            // Add image path if available
            if (data.image_path) {
                entry.image_path = data.image_path;
            }
        } else if (type === 'selected_text') {
            // Add selection metadata
            if (data.selection_metadata) {
                entry.selection_metadata = data.selection_metadata;
            }
            // Mark source explicitly
            entry.source = 'user_selection';
        }

        this.entries.push(entry);
        console.log(`[SessionManager] Added ${type} entry: ${entry.id}`);

        // Auto-save to storage after every entry
        this.autoSave(false);
    }

    /**
     * Automatically save session data to chrome.storage.local AND backend file system
     * @param {boolean} triggerPipeline - Whether to trigger the backend pipeline immediately
     */
    async autoSave(triggerPipeline = false) {
        console.log('[SessionManager] autoSave() called, enabled:', this.autoSaveEnabled);
        if (!this.autoSaveEnabled) return;

        const sessionData = this.getSessionData();

        // Save to chrome.storage.local (backup)
        chrome.storage.local.set({
            [`session_${this.sessionId}`]: sessionData,
            'current_session_id': this.sessionId
        }, () => {
            if (chrome.runtime.lastError) {
                console.error('[SessionManager] Auto-save to storage failed:', chrome.runtime.lastError);
            } else {
                console.log(`[SessionManager] Auto-saved to storage: ${this.entries.length} entries`);
            }
        });

        // Save to backend file system (primary)
        try {
            const response = await fetch('http://localhost:8000/api/save-session', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_data: sessionData,
                    session_id: this.sessionId,
                    trigger_pipeline: triggerPipeline
                })
            });

            if (response.ok) {
                const result = await response.json();
                console.log(`[SessionManager] ✅ Saved to file: ${result.filepath}`);
            } else {
                console.error('[SessionManager] Backend save failed:', response.status);
            }

            // Start polling for results ONLY if we triggered the pipeline
            if (response.ok && triggerPipeline) {
                this.pollResults(this.sessionId);
            }
        } catch (error) {
            console.error('[SessionManager] Backend save error:', error);
            // Continue even if backend save fails - we have chrome.storage backup
        }
    }

    /**
     * Poll backend for pipeline results
     */
    async pollResults(sessionId) {
        // Debounce polling to avoid multiple loops for same session
        if (this.isPolling && this.currentPollingSession === sessionId) return;

        this.isPolling = true;
        this.currentPollingSession = sessionId;
        console.log(`[SessionManager] Polling results for session ${sessionId}...`);

        const maxAttempts = 30; // 60 seconds
        let attempts = 0;

        const pollInterval = setInterval(async () => {
            attempts++;
            try {
                // If session changed, stop polling for old one
                if (this.sessionId !== sessionId) {
                    console.log('[SessionManager] Session changed, stopping polling for', sessionId);
                    clearInterval(pollInterval);
                    this.isPolling = false;
                    return;
                }

                const response = await fetch(`http://localhost:8000/api/results/${sessionId}`);
                if (response.ok) {
                    const result = await response.json();

                    // Check if complete (stage 5 done)
                    if (result && result.stage === 5) {
                        console.log('[SessionManager] Pipeline results received:', result);
                        clearInterval(pollInterval);
                        this.isPolling = false;

                        // Display results
                        if (window.factCheckOverlay) {
                            console.log('[SessionManager] Calling showPipelineResult on global overlay');
                            window.factCheckOverlay.showPipelineResult(result);
                        } else {
                            console.error('[SessionManager] window.factCheckOverlay is missing!');
                        }
                    }
                } else if (response.status === 404) {
                    // Result not ready yet, continue polling
                } else {
                    // Error
                    console.error('[SessionManager] Polling error status:', response.status);
                }

                if (attempts >= maxAttempts) {
                    console.log('[SessionManager] Polling timed out');
                    clearInterval(pollInterval);
                    this.isPolling = false;
                }
            } catch (err) {
                // console.error('[SessionManager] Polling error:', err);
                // Ignore network errors during polling
                if (attempts >= maxAttempts) {
                    clearInterval(pollInterval);
                    this.isPolling = false;
                }
            }
        }, 2000);
    }

    /**
     * reset the session
     */
    resetSession() {
        this.sessionId = `session_${Date.now()}`;
        this.startTime = new Date().toISOString();
        this.entries = [];
        console.log(`SessionManager reset: ${this.sessionId}`);

        // Clear old session from storage and save new empty session
        this.autoSave(false);
    }

    /**
     * Export the session data as a JSON object
     * @returns {Object} Structured session data
     */
    getSessionData() {
        return {
            session_id: this.sessionId,
            type: "combined_session",
            start_time: this.startTime,
            entries: this.entries,
            last_updated: new Date().toISOString()
        };
    }

    /**
     * Trigger a file download of the session JSON
     */
    exportJSON() {
        const data = this.getSessionData();
        const jsonStr = JSON.stringify(data, null, 2);
        const blob = new Blob([jsonStr], { type: "application/json" });
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = `subtitle_session_${this.sessionId}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    /**
     * Load session from chrome.storage.local
     */
    async loadSession(sessionId) {
        return new Promise((resolve) => {
            chrome.storage.local.get([`session_${sessionId}`], (result) => {
                if (chrome.runtime.lastError) {
                    console.error('[SessionManager] Load failed:', chrome.runtime.lastError);
                    resolve(null);
                } else {
                    const sessionData = result[`session_${sessionId}`];
                    if (sessionData) {
                        this.sessionId = sessionData.session_id;
                        this.startTime = sessionData.start_time;
                        this.entries = sessionData.entries || [];
                        console.log(`[SessionManager] Loaded session with ${this.entries.length} entries`);
                    }
                    resolve(sessionData);
                }
            });
        });
    }

    /**
     * Finalize the session when pipeline stops
     * Forces a save and ensures polling happens for the final result
     */
    async finalizeSession() {
        console.log('[SessionManager] Finalizing session...');
        // Force a save to ensure backend has everything
        await this.autoSave(true);

        // Explicitly start polling for the final result
        if (this.entries.length > 0) {
            this.pollResults(this.sessionId);
        }
    }
}

// Make available globally
if (typeof window !== 'undefined') {
    window.SessionManager = SessionManager;
}
