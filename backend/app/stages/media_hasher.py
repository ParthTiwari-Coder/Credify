"""
Media Hasher: Perceptual Hashing (pHash) for Images and Video Keyframes
Detects repetition of media even when resized, cropped, or compressed
"""

import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image
import imagehash
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class MediaHasher:
    """
    Generates perceptual hashes for images and video keyframes
    Uses pHash algorithm to detect similar media despite transformations
    """
    
    def __init__(self, hash_threshold: int = 5):
        """
        Initialize media hasher
        
        Args:
            hash_threshold: Maximum Hamming distance for similarity (default 5)
                           Lower values = stricter matching
        """
        self.hash_threshold = hash_threshold
        logger.info(f"MediaHasher initialized with threshold={hash_threshold}")
    
    def hash_image(self, image_path: str) -> Optional[str]:
        """
        Generate perceptual hash for an image
        
        Args:
            image_path: Path to image file
            
        Returns:
            Hexadecimal hash string, or None if failed
        """
        try:
            image = Image.open(image_path)
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Generate perceptual hash (pHash)
            phash = imagehash.phash(image, hash_size=16)
            hash_str = str(phash)
            
            logger.debug(f"Generated hash for {image_path}: {hash_str[:16]}...")
            return hash_str
        except Exception as e:
            logger.error(f"Failed to hash image {image_path}: {e}")
            return None
    
    def hash_video_keyframes(self, video_path: str, 
                            interval_seconds: int = 5) -> List[Tuple[str, float]]:
        """
        Extract keyframes from video and generate hashes
        
        Args:
            video_path: Path to video file
            interval_seconds: Extract one frame every N seconds (default 5)
            
        Returns:
            List of tuples: (hash_string, timestamp_seconds)
        """
        hashes = []
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"Failed to open video: {video_path}")
                return hashes
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                fps = 30  # Default fallback
            
            frame_interval = int(fps * interval_seconds)
            frame_count = 0
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Extract frame at intervals
                if frame_count % frame_interval == 0:
                    timestamp = frame_count / fps
                    
                    # Convert BGR to RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil_image = Image.fromarray(frame_rgb)
                    
                    # Generate hash
                    phash = imagehash.phash(pil_image, hash_size=16)
                    hash_str = str(phash)
                    
                    hashes.append((hash_str, timestamp))
                    logger.debug(f"Extracted keyframe at {timestamp:.1f}s: {hash_str[:16]}...")
                
                frame_count += 1
            
            cap.release()
            logger.info(f"Extracted {len(hashes)} keyframes from {video_path}")
            return hashes
            
        except Exception as e:
            logger.error(f"Failed to hash video {video_path}: {e}")
            return hashes
    
    def compare_hashes(self, hash1: str, hash2: str) -> Tuple[int, float]:
        """
        Compare two hashes using Hamming distance
        
        Args:
            hash1: First hash string
            hash2: Second hash string
            
        Returns:
            Tuple: (hamming_distance, similarity_score)
                   similarity_score is 1.0 for identical, 0.0 for very different
        """
        if len(hash1) != len(hash2):
            logger.warning(f"Hash length mismatch: {len(hash1)} vs {len(hash2)}")
            return (max(len(hash1), len(hash2)), 0.0)
        
        distance = sum(c1 != c2 for c1, c2 in zip(hash1, hash2))
        max_distance = len(hash1)
        similarity = 1.0 - (distance / max_distance)
        
        return (distance, similarity)
    
    def is_similar(self, hash1: str, hash2: str) -> bool:
        """
        Check if two hashes are similar (within threshold)
        
        Args:
            hash1: First hash string
            hash2: Second hash string
            
        Returns:
            True if Hamming distance <= threshold
        """
        distance, _ = self.compare_hashes(hash1, hash2)
        return distance <= self.hash_threshold
    
    def process_session_media(self, session_data: Dict, 
                             sessions_dir: Path) -> Dict:
        """
        Process all media in a session and generate hashes
        
        Args:
            session_data: Session JSON data
            sessions_dir: Base directory for session files
            
        Returns:
            Dictionary with repetition detection results:
            {
                "repetition_detection": {
                    "seen_before": bool,
                    "first_seen": "YYYY-MM",
                    "platforms": [str],
                    "similarity_score": float
                },
                "media_hashes": [
                    {
                        "media_path": str,
                        "hash": str,
                        "media_type": "image" | "video",
                        "matches": [dict]  # Similar hashes found
                    }
                ]
            }
        """
        logger.info("Processing session media for hashing")
        
        session_id = session_data.get('session_id', 'unknown')
        entries = session_data.get('entries', [])
        
        # Extract unique image IDs from entries
        image_ids = set()
        for entry in entries:
            if entry.get('source') == 'image' and entry.get('image_id'):
                image_ids.add(entry['image_id'])
        
        media_results = []
        all_matches = []
        
        # Process each image
        for image_id in image_ids:
            image_path = sessions_dir / "images" / f"{image_id}.jpg"
            
            if not image_path.exists():
                logger.warning(f"Image not found: {image_path}")
                continue
            
            # Generate hash
            hash_value = self.hash_image(str(image_path))
            if not hash_value:
                continue
            
            # Store media result
            media_result = {
                "media_path": str(image_path),
                "hash": hash_value,
                "media_type": "image",
                "image_id": image_id
            }
            
            media_results.append(media_result)
        
        # Check for matches (this will be done by database in full implementation)
        # For now, return structure
        repetition_detection = {
            "seen_before": len(all_matches) > 0,
            "first_seen": None,
            "platforms": [],
            "similarity_score": 0.0
        }
        
        if all_matches:
            # Get earliest match
            earliest = min(all_matches, key=lambda x: x.get('first_seen', ''))
            repetition_detection["first_seen"] = earliest.get('first_seen', '')[:7]  # YYYY-MM
            repetition_detection["platforms"] = earliest.get('platforms_seen', [])
            repetition_detection["similarity_score"] = earliest.get('similarity_score', 0.0)
        
        return {
            "repetition_detection": repetition_detection,
            "media_hashes": media_results
        }

