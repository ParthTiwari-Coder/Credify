"""
Fact-Checking Agent System - Main Orchestrator
Coordinates the 6-stage pipeline for fact-checking (Stage 0 added for media analysis)
"""

import logging
import os
from pathlib import Path
from typing import Dict
try:
    from utils.gemini_client import GeminiClient
    from stages import (
        MediaAnalyzer,
        ClaimExtractor,
        TrustScorer,
        SemanticDetector,
        FactVerifier,
        Explainer
    )
except ImportError:
    from .utils.gemini_client import GeminiClient
    from .stages import (
        MediaAnalyzer,
        ClaimExtractor,
        TrustScorer,
        SemanticDetector,
        FactVerifier,
        Explainer
    )

logger = logging.getLogger(__name__)


class FactChecker:
    """
    Main orchestrator for the 6-stage fact-checking pipeline
    
    Pipeline:
    0. Media Analysis (Hashing + Reverse Search)
    1. Claim Selection & Extraction (Gemini LLM)
    2. Rule-Based Suspicion Flags + Trust Score
    3. Plagiarism / Rewritten Fake Detection (Gemini embeddings)
    4. Decision Gate + Deep Fact Verification (Gemini analysis)
    5. Explanation & Final Output
    """
    
    def __init__(self, gemini_api_key: str, serpapi_api_key: str = None):
        """
        Initialize fact-checking system
        
        Args:
            gemini_api_key: Gemini API key
            serpapi_api_key: SerpAPI API key for Google reverse image search (optional, can use env var)
        """
        logger.info("Initializing Fact-Checking System")
        
        # Initialize Gemini client
        self.gemini = GeminiClient(gemini_api_key)
        
        # Initialize all stages
        self.stage0 = MediaAnalyzer(serpapi_api_key=serpapi_api_key)
        self.stage1 = ClaimExtractor(self.gemini)
        self.stage2 = TrustScorer()
        self.stage3 = SemanticDetector(self.gemini)
        self.stage4 = FactVerifier(self.gemini)
        self.stage5 = Explainer()
        
        logger.info("Fact-Checking System initialized successfully")
    
    def process_session(self, session_data: Dict) -> Dict:
        """
        Process session JSON through the complete 5-stage pipeline
        
        Args:
            session_data: Raw session JSON from browser extension
            
        Returns:
            Final output with verified claims, verdicts, and explanations
        """
        session_id = session_data.get('session_id', 'unknown')
        logger.info(f"=" * 80)
        logger.info(f"Processing session: {session_id}")
        logger.info(f"=" * 80)
        
        try:
            # STAGE 0: Media Analysis (Hashing + Reverse Search)
            # Only run if session contains images (OCR screenshots or video keyframes)
            has_images = self._has_images(session_data)
            
            if has_images:
                logger.info("\n[STAGE 0] Media Analysis")
                logger.info("-" * 80)
                # Determine sessions directory
                base_path = Path(__file__).parent.parent  # backend root
                sessions_dir = base_path / "sessions"
                media_analysis = self.stage0.analyze_media(session_data, sessions_dir)
                # Attach media analysis to session_data for use in later stages
                session_data['media_analysis'] = media_analysis
                logger.info(f"Stage 0 complete: Media analysis finished")
            else:
                logger.info("\n[STAGE 0] Skipped (no images in session)")
                session_data['media_analysis'] = {
                    "repetition_detection": {"seen_before": False},
                    "context_verification": {"context_mismatch": False}
                }
            
            # Save Stage 0 Result (Media Analysis + OCR Entries)
            # This ensures we capture what SerpAPI found AND what OCR extracted
            stage_0_result = {
                "media_analysis": session_data.get('media_analysis', {}),
                "entries": session_data.get('entries', [])  # Include OCR text
            }
            self._save_stage_result(session_id, 0, stage_0_result)
            
            # STAGE 1: Claim Selection & Extraction
            logger.info("\n[STAGE 1] Claim Selection & Extraction")
            logger.info("-" * 80)
            claims_data = self.stage1.extract_claims(session_data)
            logger.info(f"Stage 1 complete: {len(claims_data['claims'])} claims extracted")
            
            if not claims_data['claims']:
                logger.info("No claims found. Ending pipeline.")
                no_claims_result = {
                    "session_id": session_id,
                    "status": "no_claims",
                    "total_claims": 0,
                    "claims": [],
                    "flagged_terms": claims_data.get('flagged_terms', [])
                }
                # Save final result so frontend stops polling
                self._save_stage_result(session_id, 5, no_claims_result, is_final=True)
                return no_claims_result
            
            # STAGE 2: Rule-Based Suspicion Flags + Trust Score
            logger.info("\n[STAGE 2] Rule-Based Suspicion Flags + Trust Score")
            logger.info("-" * 80)
            scored_claims = self.stage2.score_claims(claims_data, session_data)
            logger.info(f"Stage 2 complete: Trust scores calculated")
            self._save_stage_result(session_id, 2, scored_claims)
            
            # STAGE 3: Plagiarism / Rewritten Fake Detection
            logger.info("\n[STAGE 3] Plagiarism / Rewritten Fake Detection")
            logger.info("-" * 80)
            detected_claims = self.stage3.detect_rewritten_misinfo(scored_claims)
            logger.info(f"Stage 3 complete: Semantic detection finished")
            self._save_stage_result(session_id, 3, detected_claims)
            
            # STAGE 4: Decision Gate + Deep Fact Verification
            logger.info("\n[STAGE 4] Decision Gate + Deep Fact Verification")
            logger.info("-" * 80)
            verified_claims = self.stage4.verify_claims(detected_claims)
            logger.info(f"Stage 4 complete: Verification finished")
            self._save_stage_result(session_id, 4, verified_claims)
            
            # STAGE 5: Explanation & Final Output
            logger.info("\n[STAGE 5] Explanation & Final Output")
            logger.info("-" * 80)
            final_output = self.stage5.generate_explanations(verified_claims, session_data)
            logger.info(f"Stage 5 complete: Explanations generated")
            
            # Add flagged terms to final output
            final_output['flagged_terms'] = claims_data.get('flagged_terms', [])
            
            # Save final result
            self._save_stage_result(session_id, 5, final_output, is_final=True)
            
            # Add session metadata to output
            final_output['session_id'] = session_id
            final_output['status'] = 'success'
            final_output['total_claims'] = len(final_output['claims'])
            
            logger.info(f"\n{'=' * 80}")
            logger.info(f"Pipeline complete for session {session_id}")
            logger.info(f"Total claims processed: {final_output['total_claims']}")
            logger.info(f"{'=' * 80}\n")
            
            return final_output
            
        except Exception as e:
            logger.error(f"Pipeline failed for session {session_id}: {str(e)}", exc_info=True)
            return {
                "session_id": session_id,
                "status": "error",
                "error": str(e),
                "claims": []
            }
    
    def process_single_claim(self, claim_text: str, domain: str = "general") -> Dict:
        """
        Process a single claim (for testing/debugging)
        
        Args:
            claim_text: The claim to verify
            domain: Domain category
            
        Returns:
            Verification result
        """
        # Create minimal session data
        session_data = {
            "session_id": "single_claim_test",
            "entries": [
                {
                    "id": "test_1",
                    "text": claim_text
                }
            ]
        }
        
        return self.process_session(session_data)
    
    def _has_images(self, session_data: Dict) -> bool:
        """
        Check if session contains images (OCR screenshots or video keyframes)
        
        Args:
            session_data: Session JSON data
            
        Returns:
            True if session has images, False otherwise
        """
        entries = session_data.get('entries', [])
        for entry in entries:
            # Check for image_id (from OCR screenshots or video keyframes)
            if entry.get('image_id') or entry.get('image_path'):
                return True
            # Check for screen_ocr source (which includes images)
            if entry.get('source') == 'image' or entry.get('source') == 'screen_capture' or entry.get('source') == 'video_keyframe':
                return True
        return False
    
    def _save_stage_result(self, session_id: str, stage_num: int, result: Dict, is_final: bool = False):
        """
        Save stage result to results folder
        
        Args:
            session_id: Session ID
            stage_num: Stage number (0-5)
            result: Result dictionary to save
            is_final: Whether this is the final result
        """
        try:
            base_path = Path(__file__).parent.parent.parent  # results are in project root
            results_dir = base_path / "results"
            results_dir.mkdir(exist_ok=True)
            
            # Add metadata
            result_with_meta = {
                **result,
                "session_id": session_id,
                "stage": stage_num,
                "timestamp": str(Path(__file__).stat().st_mtime)  # Simple timestamp
            }
            
            # Save file
            if is_final:
                filename = f"final_result_{session_id}.json"
            else:
                filename = f"stage_{stage_num}_{session_id}.json"
            
            filepath = results_dir / filename
            import json
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(result_with_meta, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Saved stage {stage_num} result to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save stage {stage_num} result: {e}")
