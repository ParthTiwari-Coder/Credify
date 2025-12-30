// API client for backend communication
class APIClient {
  constructor(baseURL = CONFIG.API_BASE_URL) {
    this.baseURL = baseURL;
    this.requestQueue = [];
    this.isProcessing = false;
  }

  /**
   * Process OCR on image/frame
   * @param {string} imageBase64 - Base64 encoded image
   * @param {Object} options - OCR options
   * @returns {Promise<Object>} OCR result
   */
  async processOCR(imageBase64, options = {}) {
    const endpoint = `${this.baseURL}/api/ocr`;
    
    const payload = {
      image: imageBase64,
      target_language: options.targetLanguage || null,
      enable_translation: options.enableTranslation || false,
      timestamp: options.timestamp || null,
      source: options.source || 'unknown'
    };

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error(`API Error: ${response.status} ${response.statusText}`);
      }

      const result = await response.json();
      return this.validateOCRResult(result);
    } catch (error) {
      console.error('OCR API Error:', error);
      throw error;
    }
  }

  /**
   * Batch process multiple frames
   * @param {Array<Object>} frames - Array of frame data
   * @param {Object} options - Processing options
   * @returns {Promise<Array<Object>>} Array of OCR results
   */
  async processBatch(frames, options = {}) {
    const endpoint = `${this.baseURL}/api/ocr/batch`;
    
    const payload = {
      frames: frames.map(frame => ({
        image: frame.imageBase64,
        timestamp: frame.timestamp,
        source: frame.source
      })),
      target_language: options.targetLanguage || null,
      enable_translation: options.enableTranslation || false
    };

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error(`API Error: ${response.status}`);
      }

      const results = await response.json();
      return results.map(result => this.validateOCRResult(result));
    } catch (error) {
      console.error('Batch OCR API Error:', error);
      throw error;
    }
  }

  /**
   * Validate OCR result format
   * @param {Object} result - OCR result from API
   * @returns {Object} Validated result
   */
  validateOCRResult(result) {
    if (!result) {
      throw new Error('Empty OCR result');
    }

    // Ensure required fields exist
    const validated = {
      timestamp: result.timestamp || '00:00:00',
      detected_language: result.detected_language || 'unknown',
      original_text: result.original_text || '',
      translated_text: result.translated_text || result.original_text || '',
      confidence: result.confidence || 0,
      source: result.source || 'unknown',
      text_regions: result.text_regions || []
    };

    // Filter low confidence results
    if (validated.confidence < CONFIG.MIN_CONFIDENCE) {
      console.warn(`Low confidence result: ${validated.confidence}`);
    }

    return validated;
  }

  /**
   * Check if API is available
   * @returns {Promise<boolean>} True if API is reachable
   */
  async healthCheck() {
    try {
      const response = await fetch(`${this.baseURL}/health`, {
        method: 'GET',
        timeout: 5000
      });
      
      return response.ok;
    } catch (error) {
      console.error('Health check failed:', error);
      return false;
    }
  }

  /**
   * Get supported languages
   * @returns {Promise<Array<Object>>} Array of supported languages
   */
  async getSupportedLanguages() {
    try {
      const response = await fetch(`${this.baseURL}/api/languages`, {
        method: 'GET'
      });

      if (!response.ok) {
        throw new Error('Failed to fetch languages');
      }

      return await response.json();
    } catch (error) {
      console.error('Error fetching languages:', error);
      // Return default languages from config
      return Object.entries(CONFIG.SUPPORTED_LANGUAGES).map(([code, name]) => ({
        code,
        name
      }));
    }
  }

  /**
   * Add request to queue (for rate limiting)
   * @param {Function} requestFn - Request function
   * @returns {Promise<any>} Request result
   */
  async queueRequest(requestFn) {
    return new Promise((resolve, reject) => {
      this.requestQueue.push({ requestFn, resolve, reject });
      this.processQueue();
    });
  }

  /**
   * Process queued requests
   */
  async processQueue() {
    if (this.isProcessing || this.requestQueue.length === 0) {
      return;
    }

    this.isProcessing = true;
    const { requestFn, resolve, reject } = this.requestQueue.shift();

    try {
      const result = await requestFn();
      resolve(result);
    } catch (error) {
      reject(error);
    } finally {
      this.isProcessing = false;
      
      // Process next request after small delay
      if (this.requestQueue.length > 0) {
        setTimeout(() => this.processQueue(), 100);
      }
    }
  }

  /**
   * Get queue statistics
   * @returns {Object} Queue stats
   */
  getQueueStats() {
    return {
      queueLength: this.requestQueue.length,
      isProcessing: this.isProcessing
    };
  }
}

// Make available globally
if (typeof window !== 'undefined') {
  window.APIClient = APIClient;
}