const recentTexts = new Set();
const MAX_CACHE = 20;

function isNewContent(text) {
  if (!text || !text.trim()) return false;
  const normalized = text.trim().toLowerCase();
  if (recentTexts.has(normalized)) return false;

  recentTexts.add(normalized);
  if (recentTexts.size > MAX_CACHE) {
    const first = recentTexts.values().next().value;
    recentTexts.delete(first);
  }
  return true;
}

if (typeof window !== 'undefined') {
  window.isNewContent = isNewContent;
}
