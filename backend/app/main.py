"""
TrueLens Backend - All-in-One
FastAPI backend with OCR, STT, Translation, and Language Detection
"""

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
import base64
import io
import os
import json
import tempfile
from pathlib import Path
from PIL import Image
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# OCR imports
import cv2
import easyocr
import numpy as np

# Language detection
import langid

# Translation
from googletrans import Translator as GoogleTranslator
from functools import lru_cache
import time

# Speech-to-Text
import whisper
import torch
from pydub import AudioSegment

# Fact-Checking System
try:
    from fact_checker import FactChecker
except ImportError:
    from .fact_checker import FactChecker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# OCR ENGINE
# ============================================================================

class OCREngine:
    def __init__(self):
        """Initialize OCR with multiple language readers"""
        try:
            logger.info("Loading OCR Models...")
            self.latin_reader = easyocr.Reader(["en", "es", "fr"], gpu=False)
            self.hindi_reader = easyocr.Reader(["en", "hi"], gpu=False)
            self.arabic_reader = easyocr.Reader(["en", "ar"], gpu=False)
            logger.info("OCR Engines loaded successfully.")
        except Exception as e:
            logger.error(f"Error initializing EasyOCR: {e}")
            raise

    def extract_text(self, image: Image.Image) -> List[Dict]:
        """Run OCR and return structured regions"""
        cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

        for reader in (self.latin_reader, self.hindi_reader, self.arabic_reader):
            results = reader.readtext(cv_image, detail=1, paragraph=False)
            if results:
                break
        else:
            results = []

        formatted = []
        for bbox, text, conf in results:
            x_coords = [pt[0] for pt in bbox]
            y_coords = [pt[1] for pt in bbox]
            x, y = int(min(x_coords)), int(min(y_coords))
            w, h = int(max(x_coords) - x), int(max(y_coords) - y)
            formatted.append({
                "text": text.strip(),
                "confidence": float(conf),
                "bbox": [x, y, w, h],
            })
        return formatted

    def process_base64(self, base64_image: str) -> List[Dict]:
        """Process base64 encoded image"""
        image = self._decode_image(base64_image)
        if image is None:
            return []
        return self.extract_text(image)

    def _decode_image(self, base64_string: str) -> Image.Image:
        try:
            if "," in base64_string:
                base64_string = base64_string.split(",")[1]
            img_data = base64.b64decode(base64_string)
            return Image.open(io.BytesIO(img_data)).convert("RGB")
        except Exception as e:
            logger.error(f"Image decoding failed: {e}")
            return None


# ============================================================================
# LANGUAGE DETECTOR
# ============================================================================

class LanguageDetector:
    def __init__(self):
        logger.info("Language Detector initialized.")

    def detect_language_code(self, text):
        """Detect ISO 639-1 language code"""
        if not text or len(text.strip()) < 2:
            return "und"
        try:
            lang, confidence = langid.classify(text)
            logger.info(f"Detected {lang} with {confidence*100:.2f}% confidence")
            return lang
        except Exception as e:
            logger.error(f"Language detection failed: {e}")
            return "en"

    def is_target_language(self, text, target_lang_code):
        detected = self.detect_language_code(text)
        return detected == target_lang_code


# ============================================================================
# TRANSLATOR
# ============================================================================

class Translator:
    def __init__(self):
        self.translator = GoogleTranslator()
        self.max_retries = 3
        self.retry_delay = 1
        logger.info("Translator initialized")

    @lru_cache(maxsize=1000)
    def translate(self, text: str, target_lang: str, source_lang: Optional[str] = 'auto') -> Optional[str]:
        """Translate text to target language"""
        if not text or not text.strip():
            return None
        
        if source_lang != 'auto' and source_lang == target_lang:
            return text
        
        max_length = 5000
        if len(text) > max_length:
            text = text[:max_length]
        
        for attempt in range(self.max_retries):
            try:
                result = self.translator.translate(text, dest=target_lang, src=source_lang)
                logger.info(f"Translated from {result.src} to {target_lang}")
                return result.text
            except Exception as e:
                logger.error(f"Translation error (attempt {attempt + 1}): {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    return None


# ============================================================================
# SPEECH-TO-TEXT ENGINE
# ============================================================================

class SpeechToTextEngine:
    def __init__(self, model_size: str = 'tiny'):  # Changed to 'tiny' for speed
        logger.info(f"Loading Whisper model: {model_size}")
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model = whisper.load_model(model_size, device=device)
            self.device = device
            logger.info(f"Whisper model loaded on {device}")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {str(e)}")
            raise

    def transcribe_base64(self, audio_base64: str, language: Optional[str] = None, task: str = "transcribe") -> Dict:
        """Transcribe base64 encoded audio - optimized for speed"""
        audio_data = base64.b64decode(audio_base64)
        return self.transcribe(audio_data, language, task)

    def transcribe(self, audio_data: bytes, language: Optional[str] = None, task: str = "transcribe") -> Dict:
        """Transcribe audio to text - optimized version"""
        try:
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as temp_audio:
                temp_audio.write(audio_data)
                temp_audio_path = temp_audio.name
            
            # Optimized audio processing
            audio = AudioSegment.from_file(temp_audio_path)
            
            # Skip silent audio to save processing time
            if audio.dBFS < -40:  # Very quiet audio, likely silence
                logger.info("Skipping silent audio chunk")
                try:
                    os.unlink(temp_audio_path)
                except:
                    pass
                return {
                    'text': '',
                    'language': 'unknown',
                    'confidence': 0.0
                }
            
            # Normalize audio for better accuracy
            audio = audio.normalize()
            
            # Convert to mono for faster processing
            if audio.channels > 1:
                audio = audio.set_channels(1)
            
            # Resample to 16kHz (Whisper's native rate) for speed
            audio = audio.set_frame_rate(16000)
            
            wav_path = temp_audio_path.replace('.webm', '.wav')
            audio.export(wav_path, format='wav')
            
            # Optimized Whisper parameters for speed and accuracy
            result = self.model.transcribe(
                wav_path,
                language=language,
                task=task,
                fp16=self.device == "cuda",
                verbose=False,
                # Speed optimizations
                beam_size=1,  # Faster decoding
                best_of=1,    # Single pass
                temperature=0,  # Deterministic output
                # Accuracy improvements
                condition_on_previous_text=True,  # Better context
                initial_prompt="",  # Can add context here
                word_timestamps=False,  # Disable for speed
                # VAD filter for silence
                no_speech_threshold=0.6  # Skip if mostly silence
            )
            
            transcription = {
                'text': result['text'].strip(),
                'language': result.get('language', 'unknown'),
                'confidence': self._calculate_confidence(result.get('segments', []))
            }
            
            logger.info(f"Transcribed: {len(transcription['text'])} chars, lang={transcription['language']}")
            
            # Cleanup
            try:
                os.unlink(temp_audio_path)
                os.unlink(wav_path)
            except:
                pass
            
            return transcription
        except Exception as e:
            logger.error(f"Transcription error: {str(e)}")
            raise

    def _calculate_confidence(self, segments: list) -> float:
        if not segments:
            return 0.0
        try:
            # avg_logprob is typically negative (e.g. -0.5)
            # Probability = exp(avg_logprob)
            total_prob = sum(np.exp(s.get('avg_logprob', -10.0)) for s in segments)
            avg_prob = total_prob / len(segments)
            return max(0.0, min(1.0, avg_prob))
        except Exception:
            return 0.0


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="TrueLens Backend API",
    description="OCR, STT, and Translation service",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add exception handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with detailed logging"""
    logger.error(f"Validation error on {request.url.path}")
    logger.error(f"Validation errors: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "message": "Request validation failed. Please check that 'session_data' is a valid JSON object."
        }
    )

# Initialize services
ocr_engine = OCREngine()
language_detector = LanguageDetector()
translator = Translator()
stt_engine = SpeechToTextEngine(model_size='tiny')  # Faster model

# Initialize fact-checking system (lazy loading to avoid startup delay)
fact_checker = None

def get_fact_checker():
    """Lazy initialization of fact-checker"""
    global fact_checker
    if fact_checker is None:
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            raise HTTPException(
                status_code=500,
                detail="GEMINI_API_KEY not configured. Set environment variable to use fact-checking."
            )
        serpapi_key = os.getenv("SERPAPI_API_KEY")  # Optional for Stage 0 reverse search
        fact_checker = FactChecker(gemini_key, serpapi_api_key=serpapi_key)
    return fact_checker

def run_pipeline_background(session_data: dict, session_id: str):
    """Run fact-checking pipeline in background"""
    logger.info(f"Starting background pipeline for session {session_id}")
    try:
        checker = get_fact_checker()
        checker.process_session(session_data)
        logger.info(f"Background pipeline finished for session {session_id}")
    except Exception as e:
        logger.error(f"Background pipeline failed for session {session_id}: {e}")


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class OCRRequest(BaseModel):
    image: str = Field(..., description="Base64 encoded image")
    target_language: Optional[str] = Field(None, description="Target language code")
    enable_translation: bool = Field(False, description="Enable translation")
    timestamp: Optional[str] = Field(None, description="Video timestamp")
    source: str = Field("unknown", description="Source type")

class TextRegion(BaseModel):
    text: str
    confidence: float
    bbox: List[int]

class OCRResponse(BaseModel):
    timestamp: str
    detected_language: str
    original_text: str
    translated_text: Optional[str] = None
    confidence: float
    source: str
    text_regions: List[TextRegion] = Field(default_factory=list)

class STTRequest(BaseModel):
    audio: str = Field(..., description="Base64 encoded audio")
    target_language: Optional[str] = Field(None, description="Target language")
    enable_translation: bool = Field(False, description="Enable translation")
    source: str = Field("tab_audio", description="Source of audio")

class STTResponse(BaseModel):
    timestamp: str
    source: str
    detected_language: str
    original_text: str
    translated_text: Optional[str] = None
    confidence: float

class SaveSessionRequest(BaseModel):
    session_data: dict = Field(..., description="Complete session data")
    session_id: str = Field(..., description="Session ID")
    trigger_pipeline: bool = Field(True, description="Whether to trigger the pipeline immediately")

class SaveImageRequest(BaseModel):
    image_data: str = Field(..., description="Base64 encoded image")
    image_id: str = Field(..., description="Unique image ID")
    source: str = Field("screen_capture", description="Source of image")

class LanguageInfo(BaseModel):
    code: str
    name: str
    native_name: str

class FactCheckRequest(BaseModel):
    session_data: dict = Field(..., description="Session JSON to fact-check")

class FactCheckResponse(BaseModel):
    session_id: str
    status: str
    total_claims: int = 0
    claims: List[Dict]
    error: Optional[str] = None


# ============================================================================
# API ROUTES
# ============================================================================

@app.get("/")
async def root():
    return {
        "message": "TrueLens Backend API",
        "version": "2.0.0",
        "endpoints": {
            "health": "/health",
            "ocr": "/api/ocr",
            "speech_to_text": "/api/speech-to-text",
            "fact_check": "/api/fact-check",
            "save_session": "/api/save-session",
            "save_image": "/api/save-image",
            "languages": "/api/languages"
        }
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "2.0.0",
        "services": {
            "ocr": "operational",
            "language_detection": "operational",
            "translation": "operational",
            "speech_to_text": "operational"
        }
    }

@app.post("/api/ocr", response_model=OCRResponse)
async def process_ocr(request: OCRRequest):
    """Process OCR on single image"""
    try:
        encoded_image = request.image
        if "," in encoded_image:
            encoded_image = encoded_image.split(",")[1]
        
        image_data = base64.b64decode(encoded_image)
        image = Image.open(io.BytesIO(image_data))
        
        ocr_results = ocr_engine.extract_text(image)
        
        if not ocr_results:
            return OCRResponse(
                timestamp=request.timestamp or "00:00:00",
                detected_language="unknown",
                original_text="",
                translated_text="",
                confidence=0.0,
                source=request.source,
                text_regions=[]
            )
        
        full_text = " ".join([region['text'] for region in ocr_results])
        avg_confidence = sum([region['confidence'] for region in ocr_results]) / len(ocr_results)
        detected_lang = language_detector.detect_language_code(full_text)
        
        translated_text = None
        if request.enable_translation and request.target_language:
            if detected_lang != request.target_language:
                translated_text = translator.translate(full_text, source_lang=detected_lang, target_lang=request.target_language)
            else:
                translated_text = full_text
        
        text_regions = [TextRegion(text=region['text'], confidence=region['confidence'], bbox=region['bbox']) for region in ocr_results]
        
        return OCRResponse(
            timestamp=request.timestamp or "00:00:00",
            detected_language=detected_lang,
            original_text=full_text,
            translated_text=translated_text,
            confidence=avg_confidence,
            source=request.source,
            text_regions=text_regions
        )
    except Exception as e:
        logger.error(f"OCR error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"OCR failed: {str(e)}")

@app.post("/api/speech-to-text", response_model=STTResponse)
async def speech_to_text(request: STTRequest):
    """Transcribe audio with Whisper"""
    try:
        transcription = stt_engine.transcribe_base64(audio_base64=request.audio, language=None, task="transcribe")
        
        detected_lang = transcription.get('language', 'unknown')
        original_text = transcription.get('text', '')
        translated_text = None
        
        if request.enable_translation and request.target_language:
            if detected_lang != request.target_language:
                translated_text = translator.translate(original_text, target_lang=request.target_language, source_lang=detected_lang)
            else:
                translated_text = original_text
        
        return STTResponse(
            timestamp="auto",
            source=request.source,
            detected_language=detected_lang,
            original_text=original_text,
            translated_text=translated_text,
            confidence=transcription.get('confidence', 0.0)
        )
    except Exception as e:
        logger.error(f"STT error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"STT failed: {str(e)}")

@app.post("/api/save-session")
async def save_session(request: SaveSessionRequest, background_tasks: BackgroundTasks):
    """Save session JSON to project folder"""
    try:
        project_root = Path(__file__).parent.parent
        sessions_dir = project_root / "sessions"
        sessions_dir.mkdir(exist_ok=True)
        
        filename = f"subtitle_session_{request.session_id}.json"
        filepath = sessions_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(request.session_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Session saved to: {filepath}")
        
        # Trigger background pipeline only if requested
        if request.trigger_pipeline:
            background_tasks.add_task(run_pipeline_background, request.session_data, request.session_id)
            logger.info(f"Pipeline triggered for session {request.session_id}")
        else:
            logger.info(f"Pipeline skipped for session {request.session_id} (trigger=False)")
        
        return {
            "success": True,
            "filepath": str(filepath),
            "filename": filename,
            "entries_count": len(request.session_data.get('entries', []))
        }
    except Exception as e:
        logger.error(f"Save session error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save session: {str(e)}")

@app.post("/api/save-image")
async def save_image(request: SaveImageRequest):
    """Save captured image to project folder"""
    try:
        project_root = Path(__file__).parent.parent
        images_dir = project_root / "sessions" / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        
        image_data = request.image_data
        if "," in image_data:
            image_data = image_data.split(",")[1]
        
        image_bytes = base64.b64decode(image_data)
        
        filename = f"{request.image_id}.jpg"
        filepath = images_dir / filename
        
        with open(filepath, 'wb') as f:
            f.write(image_bytes)
        
        logger.info(f"Image saved to: {filepath}")
        
        return {
            "success": True,
            "filepath": str(filepath),
            "filename": filename,
            "relative_path": f"sessions/images/{filename}"
        }
    except Exception as e:
        logger.error(f"Save image error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save image: {str(e)}")

@app.get("/api/languages", response_model=List[LanguageInfo])
async def get_supported_languages():
    """Get list of supported languages"""
    languages = [
        LanguageInfo(code="en", name="English", native_name="English"),
        LanguageInfo(code="hi", name="Hindi", native_name="हिन्दी"),
        LanguageInfo(code="ar", name="Arabic", native_name="العربية"),
        LanguageInfo(code="es", name="Spanish", native_name="Español"),
        LanguageInfo(code="fr", name="French", native_name="Français"),
        LanguageInfo(code="de", name="German", native_name="Deutsch"),
        LanguageInfo(code="zh", name="Chinese", native_name="中文"),
        LanguageInfo(code="ja", name="Japanese", native_name="日本語"),
        LanguageInfo(code="ko", name="Korean", native_name="한국어"),
        LanguageInfo(code="ru", name="Russian", native_name="Русский"),
    ]
    return languages

@app.post("/api/fact-check", response_model=FactCheckResponse)
async def fact_check_session(request: Request):
    """
    Process session JSON through the 6-stage fact-checking pipeline
    
    Stages:
    0. Media Analysis (Hashing + Reverse Search) - Only if images present
    1. Claim Selection & Extraction (Gemini LLM) - Extracts claims and flagged terms
    2. Rule-Based Suspicion Flags + Trust Score
    3. Plagiarism / Rewritten Fake Detection (Gemini embeddings)
    4. Decision Gate + Deep Fact Verification (Gemini analysis)
    5. Explanation & Final Output
    
    Results are saved to backend/results/ folder at each stage.
    
    Accepts request body in either format:
    1. {"session_data": {...}}  (wrapped format)
    2. {...}  (direct session format)
    """
    try:
        # Get request body
        body = await request.json()
        
        # Handle both wrapped and direct formats
        if "session_data" in body:
            session_data = body["session_data"]
        else:
            # Assume the entire body is the session data
            session_data = body
        
        # Validate that we have a session-like structure
        if not isinstance(session_data, dict):
            raise HTTPException(status_code=422, detail="Invalid session data format")
        
        # Get or initialize fact-checker
        checker = get_fact_checker()
        
        # Process session through pipeline
        result = checker.process_session(session_data)
        
        return FactCheckResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fact-checking error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Fact-checking failed: {str(e)}")

@app.get("/api/results/{session_id}")
async def get_results(session_id: str):
    """
    Get final results for a session
    
    Returns the final result JSON from Stage 5
    """
    try:
        project_root = Path(__file__).parent.parent.parent
        results_dir = project_root / "results"
        filepath = results_dir / f"final_result_{session_id}.json"
        
        if not filepath.exists():
            raise HTTPException(status_code=404, detail="Results not found")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            result = json.load(f)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get results: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve results: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
