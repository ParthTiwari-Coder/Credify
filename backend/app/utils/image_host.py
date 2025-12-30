import cloudinary
import cloudinary.uploader
import logging
import os
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class CloudinaryHost:
    """
    Handles image uploads to Cloudinary for temporary hosting
    required by SerpAPI Reverse Image Search.
    """
    
    def __init__(self):
        cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME')
        api_key = os.getenv('CLOUDINARY_API_KEY')
        api_secret = os.getenv('CLOUDINARY_API_SECRET')
        
        if not all([cloud_name, api_key, api_secret]):
            logger.warning("Cloudinary credentials missing. Image upload will fail.")
            self.enabled = False
        else:
            cloudinary.config(
                cloud_name=cloud_name,
                api_key=api_key,
                api_secret=api_secret
            )
            self.enabled = True
            logger.info("CloudinaryHost initialized successfully")

    def upload_image(self, image_path: str, public_id: Optional[str] = None) -> Optional[Dict]:
        """
        Uploads image to Cloudinary and returns upload result.
        
        Args:
            image_path: Path to local image file
            public_id: Optional custom public_id
            
        Returns:
            Dict containing 'secure_url', 'public_id', etc.
        """
        if not self.enabled:
            logger.error("Cloudinary not configured")
            return None
            
        try:
            logger.info(f"Uploading to Cloudinary: {image_path}")
            response = cloudinary.uploader.upload(
                image_path,
                public_id=public_id,
                folder="factcheck_temp",
                resource_type="image"
            )
            logger.info(f"Upload successful: {response.get('secure_url')}")
            return response
        except Exception as e:
            logger.error(f"Cloudinary upload failed: {e}")
            return None

    def delete_image(self, public_id: str) -> bool:
        """
        Deletes image from Cloudinary to clean up.
        """
        if not self.enabled:
            return False
            
        try:
            cloudinary.uploader.destroy(public_id)
            logger.info(f"Deleted from Cloudinary: {public_id}")
            return True
        except Exception as e:
            logger.error(f"Cloudinary deletion failed for {public_id}: {e}")
            return False
