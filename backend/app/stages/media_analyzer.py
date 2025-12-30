"""
Stage 0: Media Analysis
Orchestrates perceptual hashing and reverse search for media repetition and context detection
"""

import logging
import os
from pathlib import Path
from typing import Dict, Optional
try:
    from stages.media_hasher import MediaHasher
    from stages.reverse_search_engine import ReverseSearchEngine
    from utils.database import Database
except ImportError:
    from .media_hasher import MediaHasher
    from .reverse_search_engine import ReverseSearchEngine
    from ..utils.database import Database

logger = logging.getLogger(__name__)


class MediaAnalyzer:
    """
    Stage 0: Media Analysis
    Combines perceptual hashing and reverse search to detect:
    1. Repetition within the system (hashing)
    2. Historical context on public web (reverse search)
    """
    
    def __init__(self, 
                 enable_hashing: bool = True,
                 enable_reverse_search: bool = True,
                 hash_threshold: int = 5,
                 serpapi_api_key: Optional[str] = None):
        """
        Initialize media analyzer
        
        Args:
            enable_hashing: Enable perceptual hashing feature
            enable_reverse_search: Enable reverse search feature
            hash_threshold: Hamming distance threshold for hash matching
            serpapi_api_key: SerpAPI API key for Google reverse image search (optional, can use env var)
        """
        self.enable_hashing = enable_hashing and os.getenv('ENABLE_MEDIA_HASHING', 'true').lower() == 'true'
        self.enable_reverse_search = enable_reverse_search and os.getenv('ENABLE_REVERSE_SEARCH', 'true').lower() == 'true'
        
        # Initialize components
        self.hasher = MediaHasher(hash_threshold=hash_threshold) if self.enable_hashing else None
        self.reverse_search = ReverseSearchEngine(api_key=serpapi_api_key) if self.enable_reverse_search else None
        
        # Initialize database (will gracefully degrade if DB not available)
        try:
            self.db = Database()
        except Exception as e:
            logger.warning(f"Database initialization failed: {e}. Features will work without persistence.")
            self.db = None
        
        logger.info(f"MediaAnalyzer initialized (hashing={self.enable_hashing}, reverse_search={self.enable_reverse_search})")
    
    def analyze_media(self, session_data: Dict, sessions_dir: Optional[Path] = None) -> Dict:
        """
        Analyze all media in session for repetition and context
        
        Args:
            session_data: Session JSON data
            sessions_dir: Base directory for session files (defaults to backend/sessions)
            
        Returns:
            Dictionary with analysis results:
            {
                "repetition_detection": {
                    "seen_before": bool,
                    "first_seen": "YYYY-MM",
                    "platforms": [str],
                    "similarity_score": float
                },
                "context_verification": {
                    "oldest_known_use": "YYYY-MM-DD",
                    "matched_sources": [dict],
                    "context_mismatch": bool
                },
                "media_hashes": [dict]
            }
        """
        session_id = session_data.get('session_id', 'unknown')
        logger.info(f"[STAGE 0] Analyzing media for session {session_id}")
        
        # Determine sessions directory
        if sessions_dir is None:
            # Default: backend/sessions relative to this file
            base_path = Path(__file__).parent.parent.parent
            sessions_dir = base_path / "sessions"
        
        # Initialize results
        results = {
            "repetition_detection": {
                "seen_before": False,
                "first_seen": None,
                "platforms": [],
                "similarity_score": 0.0
            },
            "context_verification": {
                "oldest_known_use": None,
                "matched_sources": [],
                "context_mismatch": False
            },
            "media_hashes": []
        }
        
        # Step 1: Perceptual Hashing
        if self.enable_hashing and self.hasher:
            try:
                hash_results = self.hasher.process_session_media(session_data, sessions_dir)
                results["repetition_detection"] = hash_results.get("repetition_detection", results["repetition_detection"])
                results["media_hashes"] = hash_results.get("media_hashes", [])
                
                # Store hashes in database
                if self.db:
                    self._store_hashes_in_db(session_data, results["media_hashes"])
                    
                    # Check for similar hashes
                    self._check_hash_matches(session_data, results)
                
                logger.info(f"Hashing complete: {len(results['media_hashes'])} media items processed")
            except Exception as e:
                logger.error(f"Hashing failed: {e}", exc_info=True)
        else:
            logger.info("Hashing disabled")
        
        # Step 2: Reverse Search
        if self.enable_reverse_search and self.reverse_search:
            try:
                reverse_results = self.reverse_search.process_session_media(
                    session_data, 
                    results["media_hashes"],
                    sessions_dir
                )
                results["context_verification"] = reverse_results.get("context_verification", results["context_verification"])
                
                # Store reverse search results in database
                if self.db and results["media_hashes"]:
                    self._store_reverse_search_in_db(
                        session_data,
                        results["media_hashes"],
                        results["context_verification"]
                    )
                
                logger.info(f"Reverse search complete: {len(results['context_verification'].get('matched_sources', []))} sources found")
            except Exception as e:
                logger.error(f"Reverse search failed: {e}", exc_info=True)
        else:
            logger.info("Reverse search disabled")
        
        logger.info(f"[STAGE 0] Media analysis complete for session {session_id}")
        return results
    
    def _store_hashes_in_db(self, session_data: Dict, media_hashes: list):
        """Store hashes in database"""
        if not self.db:
            return
        
        session_id = session_data.get('session_id', 'unknown')
        platform = session_data.get('media_metadata', {}).get('platform')
        
        for media_hash in media_hashes:
            hash_value = media_hash.get('hash')
            media_type = media_hash.get('media_type', 'image')
            media_path = media_hash.get('media_path')
            
            if hash_value:
                self.db.store_hash(
                    hash_value=hash_value,
                    media_type=media_type,
                    media_path=media_path,
                    session_id=session_id,
                    platform=platform
                )
    
    def _check_hash_matches(self, session_data: Dict, results: Dict):
        """Check for similar hashes in database and update results"""
        if not self.db:
            return
        
        all_matches = []
        
        for media_hash in results.get("media_hashes", []):
            hash_value = media_hash.get('hash')
            media_type = media_hash.get('media_type', 'image')
            
            if hash_value:
                matches = self.db.find_similar_hashes(
                    hash_value=hash_value,
                    media_type=media_type,
                    threshold=self.hasher.hash_threshold if self.hasher else 5
                )
                all_matches.extend(matches)
        
        # Update repetition detection if matches found
        if all_matches:
            # Get best match (highest similarity)
            best_match = max(all_matches, key=lambda x: x.get('similarity_score', 0.0))
            
            results["repetition_detection"]["seen_before"] = True
            results["repetition_detection"]["similarity_score"] = best_match.get('similarity_score', 0.0)
            
            # Extract first_seen date
            first_seen = best_match.get('first_seen')
            if first_seen:
                results["repetition_detection"]["first_seen"] = str(first_seen)[:7]  # YYYY-MM
            
            # Extract platforms
            platforms = best_match.get('platforms_seen', [])
            if platforms:
                results["repetition_detection"]["platforms"] = platforms
    
    def _store_reverse_search_in_db(self, session_data: Dict, 
                                    media_hashes: list,
                                    context_verification: Dict):
        """Store reverse search results in database"""
        if not self.db:
            return
        
        session_id = session_data.get('session_id', 'unknown')
        
        # Use first media hash as reference
        if media_hashes:
            hash_value = media_hashes[0].get('hash')
            media_path = media_hashes[0].get('media_path')
            
            if hash_value:
                self.db.store_reverse_search_result(
                    hash_value=hash_value,
                    media_path=media_path,
                    session_id=session_id,
                    oldest_known_use=context_verification.get('oldest_known_use'),
                    matched_sources=context_verification.get('matched_sources', []),
                    context_mismatch=context_verification.get('context_mismatch', False)
                )

