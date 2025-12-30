"""
Stage 5: Explanation & Final Output
Generates human-readable explanations and formats final JSON output
"""

import logging
import json
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)


class Explainer:
    def __init__(self):
        """Initialize explainer"""
        # Load flag configurations for explanations
        config_path = Path(__file__).parent.parent / "config" / "flags_config.json"
        with open(config_path, 'r') as f:
            self.flag_config = json.load(f)
        
        logger.info("Explainer initialized")
    
    def generate_explanations(self, verified_claims: Dict, session_data: Dict = None) -> Dict:
        """
        Generate explanations and format final output
        
        Args:
            verified_claims: Output from Stage 4 (verified claims)
            session_data: Original session data (for Stage 0 media analysis)
            
        Returns:
            Final formatted output with explanations
        """
        logger.info(f"Generating explanations for {len(verified_claims['claims'])} claims")
        
        # Extract media analysis from session_data if available
        media_analysis = session_data.get('media_analysis', {}) if session_data else {}
        
        final_claims = []
        
        for claim in verified_claims['claims']:
            # Generate comprehensive explanation (pass media_analysis for context)
            explanation = self._build_explanation(claim, media_analysis)
            
            # Format final output
            final_claim = {
                "claim": claim['claim'],
                "verdict": claim.get('verdict', 'UNVERIFIED'),
                "trust_score": claim['trust_score'],
                "flags": claim['flags'],
                "explanation": explanation,
                "sources": claim.get('sources_cited', []),
                "metadata": {
                    "claim_id": claim['claim_id'],
                    "domain": claim['domain'],
                    "source_entry_ids": claim['source_entry_ids']
                }
            }
            
            # Add semantic match info if present
            if 'semantic_match' in claim:
                final_claim['metadata']['semantic_match'] = claim['semantic_match']
            
            # Add media analysis metadata if available
            if media_analysis:
                final_claim['metadata']['media_analysis'] = media_analysis
            
            final_claims.append(final_claim)
        
        return {"claims": final_claims}
    
    def _build_explanation(self, claim: Dict, media_analysis: Dict = None) -> str:
        """
        Build comprehensive explanation for a claim
        
        Args:
            claim: Claim data with all analysis results
            media_analysis: Stage 0 media analysis results (optional)
            
        Returns:
            Human-readable explanation
        """
        explanation_parts = []
        
        # 0. Media Analysis explanation (Stage 0)
        if media_analysis:
            media_explanation = self._build_media_explanation(media_analysis)
            if media_explanation:
                explanation_parts.append(media_explanation)
        
        # 1. Trust score explanation
        trust_score = claim['trust_score']
        flags = claim['flags']
        
        if trust_score < 40:
            explanation_parts.append(
                f"This claim has a very low trust score ({trust_score}/100) and was not verified. "
                f"Multiple suspicion indicators were detected."
            )
        elif trust_score < 70:
            explanation_parts.append(
                f"This claim has a moderate trust score ({trust_score}/100). "
                f"Some suspicion indicators were detected."
            )
        else:
            explanation_parts.append(
                f"This claim has a high trust score ({trust_score}/100). "
                f"Few or no suspicion indicators were detected."
            )
        
        # 2. Flag explanations
        if flags:
            explanation_parts.append("\n\nSuspicion indicators:")
            for flag in flags:
                flag_info = self.flag_config.get(flag, {})
                description = flag_info.get('description', 'Unknown flag')
                penalty = flag_info.get('penalty', 0)
                explanation_parts.append(f"- {flag}: {description} (-{penalty} points)")
        
        # 3. Semantic match explanation
        if 'semantic_match' in claim:
            match = claim['semantic_match']
            explanation_parts.append(
                f"\n\nThis claim is semantically similar (similarity: {match['similarity']:.2%}) "
                f"to a previously debunked claim: \"{match['matched_claim']}\". "
                f"Debunked by: {', '.join(match['debunked_by'])}."
            )
        
        # 4. Verification explanation
        if 'verification_reasoning' in claim:
            explanation_parts.append(f"\n\nVerification: {claim['verification_reasoning']}")
        
        # 5. Verdict summary
        verdict = claim.get('verdict', 'UNVERIFIED')
        verdict_explanations = {
            'TRUE': 'The claim is supported by authoritative sources.',
            'FALSE': 'The claim is contradicted by authoritative sources.',
            'MISLEADING': 'The claim contains some truth but is presented in a misleading way.',
            'UNVERIFIED': 'Insufficient authoritative information to determine the truth of this claim.',
            'SKIPPED_LOW_TRUST': 'Verification was skipped due to low trust score.'
        }
        
        explanation_parts.append(
            f"\n\nFinal verdict: {verdict}. {verdict_explanations.get(verdict, '')}"
        )
        
        return "".join(explanation_parts)
    
    def _build_media_explanation(self, media_analysis: Dict) -> str:
        """
        Build human-readable explanation for Stage 0 media analysis
        
        Args:
            media_analysis: Media analysis results from Stage 0
            
        Returns:
            Human-readable explanation string (empty if no findings)
        """
        parts = []
        
        # Repetition detection (hashing)
        repetition = media_analysis.get('repetition_detection', {})
        if repetition.get('seen_before', False):
            first_seen = repetition.get('first_seen')
            platforms = repetition.get('platforms', [])
            similarity = repetition.get('similarity_score', 0.0)
            
            parts.append("\n\nMedia Analysis:")
            parts.append("This media has been seen before in our system.")
            
            if first_seen:
                parts.append(f"First seen: {first_seen}")
            
            if platforms:
                platforms_str = ', '.join(platforms)
                parts.append(f"Previously seen on: {platforms_str}")
            
            if similarity < 1.0:
                parts.append(f"Similarity score: {similarity:.1%} (suggesting possible editing or cropping)")
        
        # Context verification (reverse search)
        context_verification = media_analysis.get('context_verification', {})
        oldest_use = context_verification.get('oldest_known_use')
        matched_sources = context_verification.get('matched_sources', [])
        context_mismatch = context_verification.get('context_mismatch', False)
        
        if oldest_use or matched_sources:
            if not parts:
                parts.append("\n\nMedia Analysis:")
            
            if oldest_use:
                parts.append(f"This media appeared online earlier (oldest known use: {oldest_use}).")
            
            if context_mismatch:
                parts.append("The media appears in different contexts online, suggesting it may be used out of context here.")
            
            if matched_sources:
                # Show top 3 sources
                top_sources = matched_sources[:3]
                parts.append("Found on:")
                for source in top_sources:
                    url = source.get('url', '')
                    date = source.get('date', '')
                    context = source.get('context', '')
                    domain = source.get('domain', '')
                    
                    source_info = f"  - {domain}"
                    if date:
                        source_info += f" ({date})"
                    if context and len(context) < 100:
                        source_info += f": {context}"
                    parts.append(source_info)
        
        return "\n".join(parts) if parts else ""
