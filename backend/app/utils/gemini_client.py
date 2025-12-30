"""
Gemini API Client for Fact-Checking System
Handles LLM calls and embedding generation using the new google.genai package
"""

import os
import logging
from typing import List, Dict, Optional
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Gemini client with new API"""
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        # Initialize client with new API
        self.client = genai.Client(api_key=self.api_key)
        logger.info("Gemini client initialized successfully with new API")
    
    def extract_claims(self, entries: List[Dict], media_analysis: Dict = None, flag_config: Dict = None) -> Dict:
        """
        Stage 1: Extract verifiable claims AND flagged terms in a single pass
        
        Args:
            entries: List of session entries
            media_analysis: Stage 0 results
            flag_config: Dictionary of flag definitions
            
        Returns:
            Dictionary with "claims" and "flagged_terms" lists
        """
        texts = []
        for entry in entries:
            text = entry.get('text', '').strip()
            if text:
                texts.append({
                    'entry_id': entry.get('id'),
                    'text': text
                })
        
        if not texts:
            return {"claims": [], "flagged_terms": []}

        # Format flags for prompt
        flag_desc = []
        if flag_config:
            for k, v in flag_config.items():
                flag_desc.append(f"- {k}: {v['description']} (Category: {v['category']})")
        flag_context = "\n".join(flag_desc) if flag_desc else "No flags configured."

        prompt = f"""You are a precise fact-checking assistant. Your task is two-fold:
1. Extract verifiable factual claims from the text.
2. Identify specific terms/phrases that match the provided suspicious flag definitions.

INPUT TEXT:
{self._format_entries(texts)}

MEDIA ANALYSIS CONTEXT:
{self._format_media_context(media_analysis)}

SUSPICIOUS FLAG DEFINITIONS:
{flag_context}

RULES FOR CLAIMS:
- Extract statements of fact (events, stats, definitions).
- IGNORE opinions, questions, greetings.
- IGNORE metadata like "Retweets", "Likes", "Twitter for iPhone", timestamps, or device info.
- IGNORE user handles (e.g. @username) unless they are the subject of the claim.
- Use Media Analysis context to extract claims about image origin/context.

RULES FOR FLAGS:
- Identify terms matching the flag definitions exactly.
- Cite the "term" containing the suspicious content.

RETURN JSON format ONLY:
{{
  "claims": [
    {{
      "claim": "exact text of claim",
      "domain": "general/medical/political/etc",
      "source_entry_ids": ["id1"]
    }}
  ],
  "flagged_terms": [
    {{
      "term": "suspicious phrase",
      "flag_name": "FLAG_NAME_FROM_LIST",
      "flag_category": "category_from_list",
      "entry_id": "id1",
      "context": "surrounding context"
    }}
  ]
}}
"""
        
        response = None
        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                )
            )
            
            cleaned_json = self._clean_json_output(response.text)
            import json
            data = json.loads(cleaned_json)
            
            # Enrich claims with IDs
            claims = data.get("claims", [])
            for i, c in enumerate(claims):
                c['claim_id'] = f"c{i+1}"
            
            logger.info(f"Extracted {len(claims)} claims and {len(data.get('flagged_terms', []))} flagged terms")
            return {
                "claims": claims,
                "flagged_terms": data.get("flagged_terms", [])
            }
            
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            
            if response:
                if hasattr(response, 'text'):
                    logger.error(f"Raw response was: {response.text}")
                    
                    # Attempt to rescue valid data from truncated JSON
                    logger.info("Attempting to rescue partial JSON data...")
                    rescued_data = self._rescue_json(response.text)
                    if rescued_data and (rescued_data.get("claims") or rescued_data.get("flagged_terms")):
                        logger.info(f"Rescued {len(rescued_data.get('claims', []))} claims and {len(rescued_data.get('flagged_terms', []))} terms")
                        
                        # Enrich rescued claims with IDs
                        for i, c in enumerate(rescued_data.get("claims", [])):
                            c['claim_id'] = f"c{i+1}_rescued"
                            
                        return rescued_data
                
            return {"claims": [], "flagged_terms": []}

    def _rescue_json(self, text: str) -> Dict:
        """Attempt to extract valid JSON objects from a truncated response"""
        import json
        import re
        
        rescued = {"claims": [], "flagged_terms": []}
        
        try:
            # 1. Try to find the claims array
            # Look for "claims": [ ...
            claims_match = re.search(r'"claims"\s*:\s*\[', text)
            if claims_match:
                start_index = claims_match.end()
                # Iterate through the string looking for matching {} brackets to find complete objects
                current_pos = start_index
                depth = 0
                obj_start = -1
                
                valid_claims = []
                
                for i in range(start_index, len(text)):
                    char = text[i]
                    if char == '{':
                        if depth == 0:
                            obj_start = i
                        depth += 1
                    elif char == '}':
                        depth -= 1
                        if depth == 0 and obj_start != -1:
                            # Found a complete object string
                            obj_str = text[obj_start:i+1]
                            try:
                                # Clean and parse this individual object
                                clean_obj_str = self._clean_json_output(obj_str)
                                obj = json.loads(clean_obj_str)
                                valid_claims.append(obj)
                            except:
                                pass # Skip malformed individual objects
                            obj_start = -1
                
                rescued["claims"] = valid_claims

            # 2. Try to find flagged_terms array (similar logic)
            flags_match = re.search(r'"flagged_terms"\s*:\s*\[', text)
            if flags_match:
                start_index = flags_match.end()
                current_pos = start_index
                depth = 0
                obj_start = -1
                
                valid_flags = []
                
                for i in range(start_index, len(text)):
                    char = text[i]
                    if char == '{':
                        if depth == 0:
                            obj_start = i
                        depth += 1
                    elif char == '}':
                        depth -= 1
                        if depth == 0 and obj_start != -1:
                            obj_str = text[obj_start:i+1]
                            try:
                                clean_obj_str = self._clean_json_output(obj_str)
                                obj = json.loads(clean_obj_str)
                                valid_flags.append(obj)
                            except:
                                pass
                            obj_start = -1
                            
                rescued["flagged_terms"] = valid_flags

        except Exception as e:
            logger.warning(f"JSON rescue failed: {e}")
            
        return rescued

    def _clean_json_output(self, raw_text: str) -> str:
        """Clean LLM output to ensure valid JSON"""
        import re
        text = raw_text.strip()
        
        # Remove markdown blocks
        if text.startswith('```'):
            lines = text.split('\n')
            # Remove first line if it's ```json or similar
            if lines[0].startswith('```'):
                lines = lines[1:]
            # Remove last line if it's ```
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            text = '\n'.join(lines)
            
        # Basic cleanup
        text = text.strip()
        
        # Remove potential JS comments // ...
        lines = [line for line in text.split('\n') if not line.strip().startswith('//')]
        text = '\n'.join(lines)
        
        # 1. Fix unquoted keys: { key: "value" } -> { "key": "value" }
        # Matches alphanumeric keys followed by colon, not already quoted
        text = re.sub(r'([{,]\s*)([a-zA-Z0-9_]+)(\s*:)', r'\1"\2"\3', text)
        
        # 2. Fix trailing commas: [ "a", "b", ] -> [ "a", "b" ]
        text = re.sub(r',\s*([}\]])', r'\1', text)
        
        return text
    
    def verify_claim(self, claim: str, domain: str, evidence_snippets: List[Dict]) -> Dict:
        """
        Stage 4: Verify claim using evidence snippets from authoritative sources
        
        Args:
            claim: The claim text
            domain: Domain category
            evidence_snippets: List of snippets from trusted sources
                               Format: [{"source": "who.int", "snippet": "..."}]
            
        Returns:
            Dict with verdict, reasoning, and sources
        """
        # Format snippets for prompt
        snippets_text = ""
        if not evidence_snippets:
            return {
                "verdict": "UNVERIFIED",
                "reasoning": "No evidence found in authoritative sources.",
                "sources_cited": []
            }
            
        for i, item in enumerate(evidence_snippets):
            snippets_text += f"[{i+1}] Source: {item.get('source', 'Unknown')}\nSnippet: {item.get('snippet', '')}\n\n"

        prompt = f"""You are a strict fact-checker. Your job is to verify a claim using ONLY the provided evidence snippets from authoritative sources.

CLAIM: "{claim}"
DOMAIN: {domain}

EVIDENCE SNIPPETS (from trusted sources):
{snippets_text}

TASK:
1. Analyze the snippets to determine if they confirm, contradict, or provide context to the claim.
2. Determine the verdict based on this logic:
   - TRUE: Evidence explicitly confirms the claim is factually accurate.
   - FALSE: Evidence explicitly contradicts the claim.
   - MISLEADING: Evidence shows the claim is missing context, exaggerated, or technically true but deceptive.
   - UNVERIFIED: The snippets are irrelevant, vague, or do not directly address the core claim.

RULES:
- DO NOT use external knowledge. Use ONLY the provided snippets.
- If snippets mention the topic but don't prove/disprove the specific claim -> UNVERIFIED.
- Cite the specific sources (e.g. "who.int", "cdc.gov") that support your verdict.

RETURN JSON ONLY:
{{
  "verdict": "TRUE" | "FALSE" | "MISLEADING" | "UNVERIFIED",
  "reasoning": "Concise explanation citing the evidence.",
  "sources_cited": ["source1", "source2"]
}}
"""
        
        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                )
            )
            
            import json
            result_text = response.text.strip()
            
            # Remove markdown code blocks if present
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:].strip()
                result_text = result_text.rsplit('```', 1)[0].strip()
            
            result = json.loads(result_text)
            
            # Enforce valid verdict
            valid_verdicts = ["TRUE", "FALSE", "MISLEADING", "UNVERIFIED"]
            if result.get("verdict") not in valid_verdicts:
                result["verdict"] = "UNVERIFIED"
                
            logger.info(f"Verification complete: {result['verdict']}")
            return result
            
        except Exception as e:
            logger.error(f"Claim verification failed: {e}")
            return {
                "verdict": "UNVERIFIED",
                "reasoning": f"Verification failed: {str(e)}",
                "sources_cited": []
            }
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for text using Gemini
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
        """
        try:
            response = self.client.models.embed_content(
                model='text-embedding-004',
                contents=text
            )
            return response.embeddings[0].values
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return []
    
    def _format_entries(self, texts: List[Dict]) -> str:
        """Format entries for prompt"""
        formatted = []
        for item in texts:
            formatted.append(f"[{item['entry_id']}]: {item['text']}")
        return "\n".join(formatted)

    def _format_media_context(self, media_analysis: Dict) -> str:
        """Format media analysis (Stage 0) for prompt"""
        if not media_analysis:
            return "No media analysis available."
        
        context_verif = media_analysis.get('context_verification', {})
        output = []
        
        if context_verif.get('matched_sources'):
            output.append(f"Reverse Search found {len(context_verif['matched_sources'])} matches.")
            for i, match in enumerate(context_verif['matched_sources'][:3]):
                output.append(f"- Source {i+1}: {match.get('title', 'Unknown')} ({match.get('source', '')}) - {match.get('date', '')}")
        
        if context_verif.get('oldest_known_use'):
            output.append(f"Oldest known use of this image: {context_verif['oldest_known_use']}")
            
        return "\n".join(output) if output else "No significant media context found."
