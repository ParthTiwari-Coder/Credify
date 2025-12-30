"""
Reverse Search Engine: SerpAPI Google Reverse Image Search Integration
Finds older appearances of media on the public web to detect context mismatches
"""

import logging
import os
import base64
import requests
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from PIL import Image
import io

logger = logging.getLogger(__name__)

# Try to import SerpAPI library, fall back to direct requests if not available
try:
    from serpapi import GoogleSearch
    SERPAPI_LIBRARY_AVAILABLE = True
except ImportError:
    SERPAPI_LIBRARY_AVAILABLE = False
    logger.warning("serpapi library not installed. Using direct API requests.")


class ReverseSearchEngine:
    """
    Performs reverse image/video search using SerpAPI Google Reverse Image Search
    Finds historical context and usage of media on the public web
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize reverse search engine
        
        Args:
            api_key: SerpAPI API key (from environment if not provided)
        """
        self.api_key = api_key or os.getenv('SERPAPI_API_KEY')
        self.endpoint = "https://serpapi.com/search"
        
        # Initialize Cloudinary Host
        from app.utils.image_host import CloudinaryHost
        self.image_host = CloudinaryHost()
        
        if not self.api_key:
            logger.warning("SerpAPI API key not found. Reverse search will be disabled.")
        else:
            logger.info("ReverseSearchEngine initialized with SerpAPI Google Reverse Image Search")
    


    def search_image(self, image_path: str) -> Optional[Dict]:
        """
        Perform reverse image search using SerpAPI Google Reverse Image Search
        
        Args:
            image_path: Path to local image file
            
        Returns:
            Dictionary with search results
        """
        if not self.api_key:
            logger.warning("API key not available, skipping reverse search")
            return None
            
        if not self.image_host.enabled:
            logger.warning("Cloudinary not configured, skipping reverse search")
            return None
        
        uploaded_image_id = None
        try:
            # 1. Upload to Cloudinary to get public URL
            public_id_base = Path(image_path).stem
            upload_result = self.image_host.upload_image(image_path, public_id=public_id_base)
            
            if not upload_result or 'secure_url' not in upload_result:
                logger.error("Failed to upload image to Cloudinary")
                return None
                
            image_url = upload_result['secure_url']
            uploaded_image_id = upload_result.get('public_id')
            logger.info(f"Image uploaded to: {image_url}")

            # 2. Perform Reverse Search via SerpAPI using image_url
            result = None
            if SERPAPI_LIBRARY_AVAILABLE:
                try:
                    logger.info("Attempting search via SerpAPI library (Google Lens)...")
                    params = {
                        'engine': 'google_lens',
                        'api_key': self.api_key,
                        'url': image_url
                    }
                    
                    search = GoogleSearch(params)
                    result = search.get_dict()
                    
                    if 'error' in result:
                        logger.warning(f"SerpAPI library returned error: {result['error']}")
                        result = None
                        
                except Exception as e:
                    logger.warning(f"SerpAPI library failed: {e}")
                    result = None
            
            # Fallback direct request
            if result is None:
                logger.info("Using direct API request (GET) for Google Lens...")
                params = {
                    'engine': 'google_lens',
                    'api_key': self.api_key,
                    'url': image_url
                }
                
                response = requests.get(
                    self.endpoint,
                    params=params,
                    timeout=30
                )
                
                if response.status_code != 200:
                    logger.error(f"SerpAPI error: {response.status_code} - {response.text}")
                    return None
                
                try:
                    result = response.json()
                except ValueError:
                    return None
            
            if 'error' in result:
                logger.error(f"SerpAPI returned error: {result['error']}")
                return None
                
            # Parse response
            return self._parse_serpapi_response(result)
            
        except Exception as e:
            logger.error(f"Reverse search failed for {image_path}: {e}")
            return None
        finally:
            # 3. Cleanup: Delete image from Cloudinary
            if uploaded_image_id:
                self.image_host.delete_image(uploaded_image_id)
    
    def search_video_keyframes(self, video_path: str, 
                               keyframe_hashes: List[tuple]) -> Optional[Dict]:
        """
        Perform reverse search on video keyframes
        
        Args:
            video_path: Path to video file
            keyframe_hashes: List of (hash, timestamp) tuples from MediaHasher
            
        Returns:
            Combined results from all keyframes
        """
        if not self.api_key:
            return None
        
        # For now, extract first keyframe and search it
        # In full implementation, would search multiple keyframes
        try:
            import cv2
            import numpy as np
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None
            
            # Extract first frame
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                return None
            
            # Save frame temporarily
            temp_path = Path(video_path).parent / f"temp_keyframe_{Path(video_path).stem}.jpg"
            cv2.imwrite(str(temp_path), frame)
            
            try:
                result = self.search_image(str(temp_path))
            finally:
                # Clean up temp file
                if temp_path.exists():
                    temp_path.unlink()
            
            return result
            
        except Exception as e:
            logger.error(f"Video keyframe search failed: {e}")
            return None
    
    def _parse_serpapi_response(self, response: Dict) -> Dict:
        """
        Parse SerpAPI Google Lens response
        
        Args:
            response: JSON response from SerpAPI
            
        Returns:
            Structured result dictionary
        """
        matched_sources = []
        oldest_date = None
        
        try:
            # DEBUG LOGGING
            logger.info(f"SerpAPI Response Keys: {list(response.keys())}")
            
            # Google Lens returns 'visual_matches'
            image_results = response.get('visual_matches', [])
            
            # Fallback to other detections
            if not image_results and 'knowledge_graph' in response:
                 logger.info(f"Found 'knowledge_graph' but relying on visual matches logic.")
                 # Sometimes knowledge graph has better info, but visual_matches is lists
            
            if not image_results:
                 logger.warning("No 'visual_matches' found in Google Lens response.")
                 # Try finding text results if any (uncommon for simple Lens)
            
            logger.info(f"Processing {len(image_results)} visual matches")

            for result in image_results:
                # Extract details from Google Lens format
                title = result.get('title', '')
                source = result.get('source', '')
                link = result.get('link', '')
                thumbnail = result.get('thumbnail', '')
                
                # Google Lens specifically often doesn't give a 'date' for every match easily
                # We might need to dig deeper if specific struct exists, but standard is title/source/link
                
                date_published = None # Lens often omits this in standard visual match list
                
                snippet = "" # Lens visual matches usually don't have snippets like text search
                context = title if title else (source if source else "No description")
                
                domain = self._extract_domain(link)
                
                # Parse date if strictly available (rare in Lens visual_matches)
                parsed_date = None
                
                matched_sources.append({
                    "url": link,
                    "date": None, # Will be hard to get from basic Lens matches
                    "context": context,
                    "domain": domain,
                    "source": source
                })
                
            # Deduplicate by URL
            unique_sources = []
            seen_urls = set()
            for s in matched_sources:
                if s['url'] not in seen_urls:
                    unique_sources.append(s)
                    seen_urls.add(s['url'])
            matched_sources = unique_sources
            
            # Determine context mismatch
            context_mismatch = len(set(s['domain'] for s in matched_sources)) > 1 if matched_sources else False
            
            return {
                "oldest_known_use": None, # Lens doesn't give dates easily for oldest use
                "matched_sources": matched_sources[:10],
                "context_mismatch": context_mismatch
            }
            
        except Exception as e:
            logger.error(f"Failed to parse SerpAPI response: {e}")
            return {
                "oldest_known_use": None,
                "matched_sources": [],
                "context_mismatch": False
            }
    
    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain name from URL"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path
            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except:
            return url
    
    def process_session_media(self, session_data: Dict, 
                             media_hashes: List[Dict],
                             sessions_dir: Path) -> Dict:
        """
        Process all media in session for reverse search
        
        Args:
            session_data: Session JSON data
            media_hashes: List of media hash results from MediaHasher
            sessions_dir: Base directory for session files
            
        Returns:
            Dictionary with context verification results:
            {
                "context_verification": {
                    "oldest_known_use": "YYYY-MM-DD",
                    "matched_sources": [dict],
                    "context_mismatch": bool
                }
            }
        """
        logger.info("Processing session media for reverse search")
        
        if not self.api_key:
            return {
                "context_verification": {
                    "oldest_known_use": None,
                    "matched_sources": [],
                    "context_mismatch": False
                }
            }
        
        # Process first image (in full implementation, would process all)
        all_matched_sources = []
        oldest_date = None
        
        for media_hash in media_hashes:
            if media_hash.get('media_type') == 'image':
                media_path = media_hash.get('media_path')
                if not media_path:
                    continue
                
                # Perform reverse search
                result = self.search_image(media_path)
                if result and result.get('matched_sources'):
                    all_matched_sources.extend(result['matched_sources'])
                    
                    # Track oldest date
                    oldest_use = result.get('oldest_known_use')
                    if oldest_use:
                        try:
                            date_obj = datetime.strptime(oldest_use, '%Y-%m-%d')
                            if oldest_date is None or date_obj < oldest_date:
                                oldest_date = date_obj
                        except:
                            pass
        
        # Format results
        oldest_known_use = oldest_date.strftime('%Y-%m-%d') if oldest_date else None
        
        # Determine context mismatch
        context_mismatch = len(set(s.get('domain', '') for s in all_matched_sources)) > 1
        
        return {
            "context_verification": {
                "oldest_known_use": oldest_known_use,
                "matched_sources": all_matched_sources[:10],  # Top 10
                "context_mismatch": context_mismatch
            }
        }

