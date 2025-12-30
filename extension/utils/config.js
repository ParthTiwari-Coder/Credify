

const CONFIG = {
  API_BASE_URL: 'http://localhost:8000',
  AUDIO_CHUNK_MS: 3000, // 2–5s chunking
  AUDIO_BITRATE: 128000,
  OCR_INTERVAL_MS: 1000, // 1 FPS
  MIN_TEXT_LENGTH: 4,
  MIN_CONFIDENCE: 0.2,
  SUBTITLE_DISPLAY_DURATION_MS: 5000,
  SUBTITLE_FADE_DURATION_MS: 400,
  SUPPORTED_LANGUAGES: {
    en: 'English',
    hi: 'Hindi',
    ar: 'Arabic',
    es: 'Spanish',
    fr: 'French'
  }
};

if (typeof window !== 'undefined') {
  window.CONFIG = CONFIG;
}

