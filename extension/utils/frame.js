function captureFrame(video) {
  try {
    const canvas = document.createElement('canvas');
    const maxWidth = 960;
    const scale = Math.min(1, maxWidth / video.videoWidth);
    canvas.width = Math.floor(video.videoWidth * scale);
    canvas.height = Math.floor(video.videoHeight * scale);

    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    return canvas.toDataURL('image/jpeg', 0.7);
  } catch (err) {
    console.error('captureFrame failed', err);
    return null;
  }
}

if (typeof window !== 'undefined') {
  window.captureFrame = captureFrame;
}
