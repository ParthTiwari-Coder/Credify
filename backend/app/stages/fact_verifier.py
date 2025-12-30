"""
Stage 4: Deep Fact Verification
Decision gate + verification using trusted sources and Gemini analysis
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


class FactVerifier:
    def __init__(self, gemini_client: GeminiClient):
        """
        Initialize fact verifier
        
        Args:
            gemini_client: Initialized Gemini client
        """
        self.gemini = gemini_client
        
        # Load trusted sources configuration
        sources_path = Path(__file__).parent.parent / "config" / "trusted_sources.json"
        with open(sources_path, 'r') as f:
            self.trusted_sources = json.load(f)
        
        logger.info("FactVerifier initialized with two-tier source system")
    
    def verify_claims(self, detected_claims: Dict) -> Dict:
        """
        Stage 4: Verify claims using decision gate and trusted sources
        
        Args:
            detected_claims: Output from Stage 3 (claims with semantic detection)
            
        Returns:
            Claims with verdicts (only for trust_score >= 40)
        """
        logger.info(f"Verifying {len(detected_claims['claims'])} claims")
        
        verified_claims = []
        
        for claim in detected_claims['claims']:
            trust_score = claim['trust_score']
            
            # DECISION GATE: Only verify if trust_score >= 40
            if trust_score < 40:
                logger.info(
                    f"Claim {claim['claim_id']} skipped (trust_score={trust_score} < 40)"
                )
                claim['verdict'] = "SKIPPED_LOW_TRUST"
                claim['verification_reasoning'] = (
                    f"Claim skipped verification due to low trust score ({trust_score}/100). "
                    "Multiple suspicion flags triggered."
                )
                verified_claims.append(claim)
                continue
            
            # Proceed with verification
            logger.info(f"Verifying claim {claim['claim_id']} (trust_score={trust_score})")
            
            # Get relevant trusted sources for this domain
            tier1_sources = self._get_tier1_sources(claim['domain'])
            
            # Use SerpAPI as an INDEXING LAYER to find relevant snippets
            evidence_snippets = self._search_trusted_sources(claim['claim'], tier1_sources)
            
            # EVIDENCE QUALITY GATE: Require at least 2 independent snippets
            if len(evidence_snippets) < 2:
                logger.warning(f"Insufficient evidence found for claim {claim['claim_id']} (only {len(evidence_snippets)} snippets)")
                claim['verdict'] = "UNVERIFIED"
                claim['verification_reasoning'] = "No authoritative evidence found in trusted sources."
                claim['sources_cited'] = []
                verified_claims.append(claim)
                continue

            # Use Gemini to analyze the claim against snippets
            verification_result = self.gemini.verify_claim(
                claim['claim'],
                claim['domain'],
                evidence_snippets
            )
            
            # Add verification results to claim
            claim['verdict'] = verification_result['verdict']
            claim['verification_reasoning'] = verification_result['reasoning']
            claim['sources_cited'] = verification_result['sources_cited']
            
            verified_claims.append(claim)
        
        return {"claims": verified_claims}
    
    def _get_tier1_sources(self, domain: str) -> List[str]:
        """Get Tier 1 authoritative sources for domain"""
        tier1 = self.trusted_sources.get('tier1_authoritative', {})
        
        # Get domain-specific sources
        sources = tier1.get(domain, [])
        
        # Add general government sources
        sources.extend(tier1.get('government', []))
        
        return list(set(sources))  # Remove duplicates
    
    def _search_trusted_sources(self, claim: str, sources: List[str]) -> List[Dict]:
        """
        Use SerpAPI to find evidence snippets from trusted domains ONLY.
        Does NOT scrape websites directly.
        
        Args:
            claim: The claim to search for
            sources: List of trusted domain names
            
        Returns:
            List of evidence snippets [{"source": "domain", "snippet": "...", "link": "..."}]
        """
        import os
        try:
            from serpapi import GoogleSearch
        except ImportError:
            logger.error("serpapi library not installed")
            return []

        api_key = os.getenv("SERPAPI_API_KEY")
        if not api_key:
            logger.error("SERPAPI_API_KEY not found")
            return []
            
        # Construct site-restricted query: "claim" site:who.int OR site:cdc.gov ...
        # Limit to first 10 sources to prevent query string overflow
        site_operators = " OR ".join([f"site:{s}" for s in sources[:10]])
        query = f'"{claim}" {site_operators}'
        
        logger.info(f"Executing trusted search: {query[:100]}...")
        
        try:
            search = GoogleSearch({
                "q": query,
                "api_key": api_key,
                "engine": "google",
                "num": 10,  # Get top 10 results
                "gl": "in", # Localization: India (can be made dynamic)
                "hl": "en"
            })
            
            results = search.get_dict()
            organic_results = results.get("organic_results", [])
            
            evidence = []
            seen_snippets = set()
            
            for res in organic_results:
                link = res.get("link", "")
                snippet = res.get("snippet", "")
                title = res.get("title", "")
                
                # Identify which trusted source this is from
                source_domain = "unknown"
                for s in sources:
                    if s in link:
                        source_domain = s
                        break
                
                # Deduplicate similar snippets
                if snippet and snippet not in seen_snippets:
                    evidence.append({
                        "source": source_domain,
                        "title": title,
                        "snippet": snippet,
                        "link": link
                    })
                    seen_snippets.add(snippet)
            
            logger.info(f"Found {len(evidence)} evidence snippets from trusted sources")
            return evidence
            
        except Exception as e:
            logger.error(f"Trusted search failed: {e}")
            return []
        

