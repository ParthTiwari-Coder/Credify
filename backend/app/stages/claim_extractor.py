"""
Stage 1: Claim Selection & Extraction
Extracts verifiable factual claims and flagged terms from session entries using Gemini LLM
"""

import logging
import json
from pathlib import Path
from typing import List, Dict
try:
    from utils.gemini_client import GeminiClient
except ImportError:
    from ..utils.gemini_client import GeminiClient

logger = logging.getLogger(__name__)


class ClaimExtractor:
    def __init__(self, gemini_client: GeminiClient):
        """
        Initialize claim extractor
        
        Args:
            gemini_client: Initialized Gemini client
        """
        self.gemini = gemini_client
        
        # Load flag configurations for flagged term extraction
        config_path = Path(__file__).parent.parent / "config" / "flags_config.json"
        with open(config_path, 'r') as f:
            self.flag_config = json.load(f)
        
        logger.info("ClaimExtractor initialized")
    
    def extract_claims(self, session_data: Dict) -> Dict:
        """
        Extract verifiable claims and flagged terms from session data
        
        Args:
            session_data: Raw session JSON with entries (may include media_analysis from Stage 0)
            
        Returns:
            Dictionary with extracted claims and flagged terms
        """
        logger.info(f"Starting claim extraction for session {session_data.get('session_id')}")
        
        entries = session_data.get('entries', [])
        
        if not entries:
            logger.warning("No entries found in session data")
            return {"claims": [], "flagged_terms": []}
        
        # Use Gemini to extract claims AND flagged terms in one go
        media_analysis = session_data.get('media_analysis', {})
        extraction_result = self.gemini.extract_claims(entries, media_analysis, self.flag_config)
        
        claims = extraction_result.get("claims", [])
        flagged_terms = extraction_result.get("flagged_terms", [])
        
        logger.info(f"Extracted {len(claims)} claims and {len(flagged_terms)} flagged terms")
        
        return {
            "claims": claims,
            "flagged_terms": flagged_terms
        }
    
    def _format_entries(self, texts: List[Dict]) -> str:
        """Format entries for prompt"""
        formatted = []
        for item in texts:
            formatted.append(f"[{item['entry_id']}]: {item['text']}")
        return "\n".join(formatted)
    
    def _is_verifiable_claim(self, text: str) -> bool:
        """
        DEPRECATED: Rule-based validation (now handled by Gemini)
        Kept for reference only
        """
        # This is now handled by Gemini LLM
        # OCR/STT data is too noisy for rule-based extraction
        pass
