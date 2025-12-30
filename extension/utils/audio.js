// Audio capture and speech-to-text utility
class AudioCapture {
  constructor() {
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.audioContext = null;
    this.analyser = null;
    this.isRecording = false;
    this.recordingInterval = null;
  }

  /**
   * Start capturing audio from video element
   * @param {HTMLVideoElement} video - Video element to capture from
   * @param {number} chunkDuration - Duration of each audio chunk in ms
   */
  async startAudioCapture(video, chunkDuration = 3000) {
    try {
      // Create audio context
      this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
      
      // Create MediaStream from video element
      const stream = video.captureStream ? 
        video.captureStream() : 
        video.mozCaptureStream();
      
      // Get only audio track
      const audioTracks = stream.getAudioTracks();
      
      if (audioTracks.length === 0) {
        throw new Error('No audio track found in video');
      }
      
      const audioStream = new MediaStream(audioTracks);
      
      // Create MediaRecorder
      const mimeType = this.getSupportedMimeType();
      this.mediaRecorder = new MediaRecorder(audioStream, {
        mimeType: mimeType,
        audioBitsPerSecond: 128000
      });
      
      // Handle data available
      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };
      
      // Handle recording stop
      this.mediaRecorder.onstop = () => {
        this.processAudioChunk();
      };
      
      // Start recording
      this.isRecording = true;
      this.startRecordingInterval(chunkDuration);
      
      console.log('Audio capture started');
      return true;
      
    } catch (error) {
      console.error('Audio capture error:', error);
      throw error;
    }
  }

  /**
   * Start interval-based recording chunks
   * @param {number} chunkDuration - Duration of each chunk
   */
  startRecordingInterval(chunkDuration) {
    // Start initial recording
    this.mediaRecorder.start();
    
    // Set interval to stop and restart recording
    this.recordingInterval = setInterval(() => {
      if (this.isRecording && this.mediaRecorder.state === 'recording') {
        this.mediaRecorder.stop();
        
        // Restart after brief pause
        setTimeout(() => {
          if (this.isRecording) {
            this.audioChunks = [];
            this.mediaRecorder.start();
          }
        }, 100);
      }
    }, chunkDuration);
  }

  /**
   * Process recorded audio chunk
   */
  async processAudioChunk() {
    if (this.audioChunks.length === 0) return;
    
    try {
      // Create blob from chunks
      const audioBlob = new Blob(this.audioChunks, { 
        type: this.getSupportedMimeType() 
      });
      
      // Convert to base64
      const base64Audio = await this.blobToBase64(audioBlob);
      
      // Send to backend for speech-to-text
      const result = await this.sendToSTT(base64Audio);
      
      // Emit event with transcription
      if (result && result.text) {
        window.dispatchEvent(new CustomEvent('audioTranscription', {
          detail: result
        }));
      }
      
    } catch (error) {
      console.error('Audio processing error:', error);
    }
  }

  /**
   * Convert blob to base64
   * @param {Blob} blob - Audio blob
   * @returns {Promise<string>} Base64 string
   */
  blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const base64 = reader.result.split(',')[1];
        resolve(base64);
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  /**
   * Send audio to backend for speech-to-text
   * @param {string} audioBase64 - Base64 encoded audio
   * @returns {Promise<Object>} Transcription result
   */
  async sendToSTT(audioBase64) {
    try {
      const response = await fetch(`${CONFIG.API_BASE_URL}/api/speech-to-text`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          audio: audioBase64,
          source: 'video_audio'
        })
      });

      if (!response.ok) {
        throw new Error(`STT API error: ${response.status}`);
      }

      return await response.json();
      
    } catch (error) {
      console.error('STT API error:', error);
      return null;
    }
  }

  /**
   * Get supported MIME type for MediaRecorder
   * @returns {string} MIME type
   */
  getSupportedMimeType() {
    const types = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4'
    ];
    
    for (const type of types) {
      if (MediaRecorder.isTypeSupported(type)) {
        return type;
      }
    }
    
    return 'audio/webm'; // fallback
  }

  /**
   * Stop audio capture
   */
  stopAudioCapture() {
    this.isRecording = false;
    
    if (this.recordingInterval) {
      clearInterval(this.recordingInterval);
      this.recordingInterval = null;
    }
    
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
    }
    
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
    
    this.audioChunks = [];
    
    console.log('Audio capture stopped');
  }

  /**
   * Check if video has audio
   * @param {HTMLVideoElement} video - Video element
   * @returns {boolean} True if has audio
   */
  hasAudio(video) {
    return video.mozHasAudio || 
           Boolean(video.webkitAudioDecodedByteCount) ||
           Boolean(video.audioTracks && video.audioTracks.length);
  }

  /**
   * Check if audio capture is supported
   * @returns {boolean} True if supported
   */
  static isSupported() {
    return !!(
      window.MediaRecorder &&
      (HTMLVideoElement.prototype.captureStream || 
       HTMLVideoElement.prototype.mozCaptureStream)
    );
  }

  /**
   * Get audio capture capabilities
   * @returns {Object} Capabilities
   */
  static getCapabilities() {
    return {
      supported: AudioCapture.isSupported(),
      mimeTypes: [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
        'audio/mp4'
      ].filter(type => MediaRecorder.isTypeSupported(type))
    };
  }
}

// Make available globally
if (typeof window !== 'undefined') {
  window.AudioCapture = AudioCapture;
}