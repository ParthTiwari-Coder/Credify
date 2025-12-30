"""
Stage 2: Rule-Based Suspicion Flags + Trust Score
Applies flags and calculates trust score based on content patterns
"""

import logging
import json
import re
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)


class TrustScorer:
    def __init__(self):
        """Initialize trust scorer with flag configurations"""
        # Load flag configurations
        config_path = Path(__file__).parent.parent / "config" / "flags_config.json"
        with open(config_path, 'r') as f:
            self.flag_config = json.load(f)
        
        logger.info(f"TrustScorer initialized with {len(self.flag_config)} flags")
    
    def score_claims(self, claims_data: Dict, session_data: Dict) -> Dict:
        """
        Apply flags and calculate trust scores for all claims
        
        Args:
            claims_data: Output from Stage 1 (extracted claims)
            session_data: Original session data for metadata
            
        Returns:
            Claims with trust scores and flags
        """
        logger.info(f"Scoring {len(claims_data['claims'])} claims")
        
        scored_claims = []
        
        for claim in claims_data['claims']:
            # Start with base score of 100
            trust_score = 100
            flags = []
            
            # Apply all flag checks
            claim_text = claim['claim']
            
            # Content pattern flags
            if self._has_sensational_language(claim_text):
                flags.append("SENSATIONAL_LANGUAGE")
            
            if self._has_absolute_assertion(claim_text):
                flags.append("ABSOLUTE_ASSERTION")
            
            if self._has_no_evidence(claim_text):
                flags.append("NO_EVIDENCE_CITED")
            
            if self._has_urgent_sharing(claim_text):
                flags.append("URGENT_SHARING")
            
            if self._has_scientific_oversimplification(claim_text, claim['domain']):
                flags.append("SCIENTIFIC_OVERSIMPLIFICATION")
            
            # Source credibility flags (based on session metadata)
            if self._has_no_clear_source(session_data):
                flags.append("NO_CLEAR_SOURCE")
            
            if self._has_misleading_caption(claim_text):
                flags.append("MISLEADING_CAPTION")
            
            # Communal/harm flags
            if self._has_communal_framing(claim_text):
                flags.append("COMMUNAL_FRAMING")
            
            if self._has_blame_assignment(claim_text):
                flags.append("BLAME_ASSIGNMENT")
            
            if self._has_incitement_risk(claim_text):
                flags.append("INCITEMENT_RISK")
            
            # Stage 0: Media Analysis flags (from hashing and reverse search)
            media_flags = self._check_media_analysis_flags(session_data)
            flags.extend(media_flags)
            
            # Calculate final trust score
            for flag in flags:
                penalty = self.flag_config[flag]['penalty']
                trust_score -= penalty
            
            # Ensure minimum score of 0
            trust_score = max(0, trust_score)
            
            scored_claims.append({
                **claim,
                'trust_score': trust_score,
                'flags': flags
            })
            
            logger.info(f"Claim {claim['claim_id']}: trust_score={trust_score}, flags={len(flags)}")
        
        return {"claims": scored_claims}
    
    # Flag detection methods
    
    def _has_sensational_language(self, text: str) -> bool:
        """Detect sensational or emotionally charged language"""
        sensational_words = [
            'shocking', 'unbelievable', 'amazing', 'incredible', 'miracle',
            'secret', 'exposed', 'revealed', 'truth', 'hidden', 'conspiracy',
            'urgent', 'breaking', 'exclusive', 'bombshell'
        ]
        text_lower = text.lower()
        return any(word in text_lower for word in sensational_words)
    
    def _has_absolute_assertion(self, text: str) -> bool:
        """Detect absolute claims without nuance"""
        absolute_words = [
            'always', 'never', 'all', 'none', 'every', 'completely',
            'totally', 'absolutely', 'definitely', 'certainly', 'guaranteed',
            'proven', 'fact', '100%'
        ]
        text_lower = text.lower()
        return any(word in text_lower for word in absolute_words)
    
    def _has_no_evidence(self, text: str) -> bool:
        """Check if claim cites no evidence"""
        evidence_indicators = [
            'study', 'research', 'according to', 'source', 'report',
            'data', 'statistics', 'expert', 'scientist', 'doctor'
        ]
        text_lower = text.lower()
        return not any(indicator in text_lower for indicator in evidence_indicators)
    
    def _has_urgent_sharing(self, text: str) -> bool:
        """Detect urgent sharing language"""
        urgent_phrases = [
            'share immediately', 'share now', 'forward this', 'spread the word',
            'before it\'s deleted', 'before they remove', 'act now', 'hurry'
        ]
        text_lower = text.lower()
        return any(phrase in text_lower for phrase in urgent_phrases)
    
    def _has_scientific_oversimplification(self, text: str, domain: str) -> bool:
        """Detect oversimplification of scientific concepts"""
        if domain not in ['medical', 'scientific', 'climate']:
            return False
        
        oversimplification_patterns = [
            r'cures? (all|everything|cancer|covid)',
            r'(prevents?|stops?) (all|any) (disease|illness)',
            r'(simple|easy) (cure|solution|fix)',
            r'just (drink|eat|take)',
        ]
        
        text_lower = text.lower()
        return any(re.search(pattern, text_lower) for pattern in oversimplification_patterns)
    
    def _has_no_clear_source(self, session_data: Dict) -> bool:
        """Check if session has no clear source attribution"""
        # Check if media metadata exists
        media_meta = session_data.get('media_metadata', {})
        return not media_meta or not media_meta.get('platform')
    
    def _has_misleading_caption(self, text: str) -> bool:
        """Detect potentially misleading captions"""
        # Check for question marks followed by strong claims
        if '?' in text and any(word in text.lower() for word in ['yes', 'no', 'definitely', 'absolutely']):
            return True
        return False
    
    def _has_communal_framing(self, text: str) -> bool:
        """Detect communal or divisive framing"""
        communal_indicators = [
            'they', 'them', 'those people', 'these people',
            'muslims', 'hindus', 'christians', 'jews',  # Religious groups
            'immigrants', 'foreigners', 'outsiders'
        ]
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in communal_indicators)
    
    def _has_blame_assignment(self, text: str) -> bool:
        """Detect blame assignment to specific groups"""
        blame_patterns = [
            r'(because of|caused by|fault of) (the )?(muslims|hindus|christians|jews|immigrants)',
            r'(they|them) (are|were) (responsible|to blame)',
        ]
        text_lower = text.lower()
        return any(re.search(pattern, text_lower) for pattern in blame_patterns)
    
    def _has_incitement_risk(self, text: str) -> bool:
        """Detect potential incitement to violence or hatred"""
        incitement_words = [
            'attack', 'destroy', 'kill', 'eliminate', 'fight back',
            'take revenge', 'punish', 'teach them a lesson'
        ]
        text_lower = text.lower()
        return any(word in text_lower for word in incitement_words)
    
    def _check_media_analysis_flags(self, session_data: Dict) -> List[str]:
        """
        Check Stage 0 media analysis results and trigger appropriate flags
        
        Args:
            session_data: Session data with media_analysis attached
            
        Returns:
            List of flag names to add
        """
        flags = []
        media_analysis = session_data.get('media_analysis', {})
        
        if not media_analysis:
            return flags
        
        # Check repetition detection (hashing)
        repetition = media_analysis.get('repetition_detection', {})
        if repetition.get('seen_before', False):
            # Media has been seen before in our system
            similarity_score = repetition.get('similarity_score', 0.0)
            platforms = repetition.get('platforms', [])
            
            # REPOSTED_ACROSS_TIME: Media seen before
            flags.append("REPOSTED_ACROSS_TIME")
            
            # CROSS_PLATFORM_RECYCLING: Seen on multiple platforms
            if len(platforms) > 1:
                flags.append("CROSS_PLATFORM_RECYCLING")
            
            # EDITED_OR_CROPPED_MEDIA: High similarity but not identical suggests editing
            if 0.85 <= similarity_score < 0.98:
                flags.append("EDITED_OR_CROPPED_MEDIA")
        
        # Check context verification (reverse search)
        context_verification = media_analysis.get('context_verification', {})
        if context_verification.get('context_mismatch', False):
            # Media appears in different context online
            flags.append("OUT_OF_CONTEXT_IMAGE")
        
        # If oldest known use exists and is significantly older, also flag REPOSTED_ACROSS_TIME
        oldest_use = context_verification.get('oldest_known_use')
        if oldest_use:
            # Check if media is being reused (heuristic: if matched sources exist)
            matched_sources = context_verification.get('matched_sources', [])
            if matched_sources:
                flags.append("REPOSTED_ACROSS_TIME")
        
        return flags
