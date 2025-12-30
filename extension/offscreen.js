let recorder;
let timer;
let chunks = [];
let isStopping = false; // Flag to prevent processing final chunk after stop

chrome.runtime.onMessage.addListener(async (msg) => {
  if (msg.type === 'START_AUDIO') {
    console.log('Received START_AUDIO', msg);
    if (!msg.streamId) {
      console.error('START_AUDIO missing streamId');
      return;
    }
    window.targetTabId = msg.tabId; // Store tabId globally
    isStopping = false; // Reset flag on start
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          mandatory: {
            chromeMediaSource: 'tab',
            chromeMediaSourceId: msg.streamId
          }
        },
        video: false
      });

      window.currentStream = stream;

      const mimeType = getSupportedMimeType();
      if (!mimeType) throw new Error('No supported MediaRecorder type');

      recorder = new MediaRecorder(stream, { mimeType });

      recorder.ondataavailable = e => e.data.size && chunks.push(e.data);

      recorder.onstop = async () => {
        // Don't process final chunk if we're stopping
        if (isStopping) {
          console.log('Skipping final audio chunk (stop requested)');
          chunks = [];
          return;
        }

        const blob = new Blob(chunks, { type: mimeType });
        chunks = [];

        const base64 = await blobToBase64(blob);
        chrome.runtime.sendMessage({
          type: 'AUDIO_CHUNK',
          payload: base64,
          tabId: window.targetTabId // Pass original tabId for routing
        });
      };

      recorder.start();

      // Reduced chunk interval for faster subtitles (was 3000ms)
      timer = setInterval(() => {
        if (recorder?.state === 'recording') {
          recorder.stop();
          recorder.start();
        }
      }, 1500);  // Faster audio chunks = less lag

    } catch (err) {
      console.error('Offscreen audio start failed', err);
    }
  }

  if (msg.type === 'STOP_AUDIO') {
    console.log('Received STOP_AUDIO - stopping recording');
    isStopping = true; // Set flag before stopping
    clearInterval(timer);

    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    }

    // access global stream variable or we need to scope it
    if (window.currentStream) {
      window.currentStream.getTracks().forEach(track => track.stop());
      window.currentStream = null;
    }

    // Clear any pending chunks
    chunks = [];
  }
});

function getSupportedMimeType() {
  return [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus'
  ].find(t => MediaRecorder.isTypeSupported(t));
}

function blobToBase64(blob) {
  return new Promise(res => {
    const r = new FileReader();
    r.onloadend = () => res(r.result.split(',')[1]);
    r.readAsDataURL(blob);
  });
}
