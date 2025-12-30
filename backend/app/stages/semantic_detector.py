"""
Stage 3: Plagiarism / Rewritten Fake Detection
Detects semantically similar misinformation using Gemini embeddings
"""

import logging
import json
from pathlib import Path
from typing import List, Dict
try:
    from utils.gemini_client import GeminiClient
    from utils.embedding_utils import find_most_similar
except ImportError:
    from ..utils.gemini_client import GeminiClient
    from ..utils.embedding_utils import find_most_similar

logger = logging.getLogger(__name__)


class SemanticDetector:
    def __init__(self, gemini_client: GeminiClient):
        """
        Initialize semantic detector
        
        Args:
            gemini_client: Initialized Gemini client
        """
        self.gemini = gemini_client
        
        # Load known misinformation database
        db_path = Path(__file__).parent.parent / "data" / "known_misinformation.json"
        with open(db_path, 'r') as f:
            self.known_misinfo = json.load(f)
        
        # Generate embeddings for known misinformation if not present
        self._ensure_embeddings()
        
        logger.info(f"SemanticDetector initialized with {len(self.known_misinfo)} known misinformation entries")
    
    def detect_rewritten_misinfo(self, scored_claims: Dict) -> Dict:
        """
        Detect rewritten misinformation using semantic similarity
        
        Args:
            scored_claims: Output from Stage 2 (claims with trust scores)
            
        Returns:
            Claims with REWRITTEN_MISINFORMATION flag if detected
        """
        logger.info(f"Checking {len(scored_claims['claims'])} claims for semantic similarity")
        
        updated_claims = []
        
        for claim in scored_claims['claims']:
            claim_text = claim['claim']
            
            # Generate embedding for this claim
            claim_embedding = self.gemini.generate_embedding(claim_text)
            
            if not claim_embedding:
                logger.warning(f"Failed to generate embedding for claim {claim['claim_id']}")
                updated_claims.append(claim)
                continue
            
            # Get embeddings of known misinformation
            known_embeddings = [item['embedding'] for item in self.known_misinfo if item['embedding']]
            
            # Find similar claims (threshold = 0.85)
            matches = find_most_similar(claim_embedding, known_embeddings, threshold=0.85)
            
            if matches:
                # Found semantically similar misinformation
                match_idx, similarity = matches[0]
                matched_misinfo = self.known_misinfo[match_idx]
                
                logger.info(
                    f"Claim {claim['claim_id']} matches known misinformation "
                    f"'{matched_misinfo['claim']}' (similarity: {similarity:.3f})"
                )
                
                # Add REWRITTEN_MISINFORMATION flag
                if 'REWRITTEN_MISINFORMATION' not in claim['flags']:
                    claim['flags'].append('REWRITTEN_MISINFORMATION')
                    claim['trust_score'] = max(0, claim['trust_score'] - 30)
                
                # Add metadata about the match
                claim['semantic_match'] = {
                    'matched_claim': matched_misinfo['claim'],
                    'similarity': similarity,
                    'debunked_by': matched_misinfo['debunked_by'],
                    'category': matched_misinfo['category']
                }
            
            updated_claims.append(claim)
        
        return {"claims": updated_claims}
    
    def _ensure_embeddings(self):
        """Generate embeddings for known misinformation if not present"""
        needs_save = False
        
        for item in self.known_misinfo:
            if item['embedding'] is None:
                logger.info(f"Generating embedding for: {item['claim']}")
                item['embedding'] = self.gemini.generate_embedding(item['claim'])
                needs_save = True
        
        # Save updated database with embeddings
        if needs_save:
            db_path = Path(__file__).parent.parent / "data" / "known_misinformation.json"
            with open(db_path, 'w') as f:
                json.dump(self.known_misinfo, f, indent=2)
            logger.info("Updated known misinformation database with embeddings")
