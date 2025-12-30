# Credify 🔍

**Real-Time Multimodal AI Fact-Checking System**

Credify is a real-time, AI-powered fact-checking system that verifies text, images, audio, and video directly inside the browser. It helps users identify misinformation, misleading claims, and out-of-context media while browsing the web — without copy-pasting content into external tools.

Credify combines a Chrome browser extension with a Python-based backend to perform multi-stage credibility analysis and provide transparent, explainable results.

---

## 🚀 Key Features

### ✅ Real-Time Verification
- Instant fact-checking directly inside the browser
- No manual copy-paste required

### 🧠 Multimodal Analysis
- **Text**: Selected text, captions, articles
- **Images**: OCR + reverse image search
- **Video**: Keyframe extraction + audio transcription
- **Audio**: Speech-to-text (Whisper)

### 📊 Trust Scoring (0–100)
Credify assigns a transparent trust score instead of binary labels, penalizing:
- Sensational or misleading language
- Lack of evidence or sources
- Reposted or out-of-context media
- Semantic similarity to known misinformation

### 🧾 Explainable AI
- Clear reasoning for each verdict
- Visible flags and penalties
- Human-readable explanations

---

## 🧩 System Architecture (High-Level)
```
Browser Extension
        ↓
Content Capture (Text / Image / Audio / Video)
        ↓
Session Builder (in-memory JSON)
        ↓
FastAPI Backend
        ↓
Multi-Stage Fact-Checking Pipeline
        ↓
Trust Score + Verdict + Explanation
        ↓
Browser Overlay UI
```

**⚠️ Note:** Session data and results are generated at runtime and are not stored in the repository.

---

## 🔄 Verification Workflow (Simplified)

1. User selects content or starts analysis
2. Browser extension captures data
3. Backend processes content through:
   - Media analysis (images only)
   - Claim extraction
   - Trust scoring
   - Semantic detection
   - Optional fact verification
4. Final verdict and explanation are returned to the UI

---

## 🛠️ Tech Stack

### Frontend
- Chrome Extension (Manifest V3)
- JavaScript, HTML, CSS

### Backend
- Python 3.8+
- FastAPI
- Google Gemini (LLM reasoning)
- Whisper (speech-to-text)
- OCR & image hashing
- Semantic embeddings

---

## 📦 Installation & Setup

### Prerequisites
- Python 3.8+
- FFmpeg (required for audio processing)

### Backend Setup
```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

pip install -r backend/app/requirement.txt
```

Create `backend/.env`:
```env
GEMINI_API_KEY=your_gemini_api_key_here
SERPAPI_API_KEY=your_serpapi_api_key_here  # optional
```

Run backend:
```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Chrome Extension Setup

1. Open `chrome://extensions`
2. Enable **Developer Mode**
3. Click **Load Unpacked**
4. Select `factcheck/extension`
5. Credify icon appears in toolbar

---

## 📁 Project Structure
```
factcheck/
├── backend/
│   ├── app/
│   │   ├── stages/
│   │   ├── main.py
│   │   └── fact_checker.py
│   └── .env
├── extension/
│   ├── content/
│   ├── background/
│   ├── popup/
│   └── manifest.json
├── README.md
└── .gitignore
```

**⚠️ Note:** Session data and results are generated at runtime and are not stored in the repository.

---

## ⚠️ Disclaimer

Credify is a research and educational prototype and does not provide medical, legal, or professional advice.

---

## 🏁 Conclusion

Credify demonstrates how multimodal AI, trust scoring, and explainable reasoning can be combined to detect misinformation in real time — directly where users consume content.
