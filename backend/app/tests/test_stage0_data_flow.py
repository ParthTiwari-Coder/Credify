
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the class we are testing
from fact_checker import FactChecker

class TestStage0DataFlow(unittest.TestCase):
    def setUp(self):
        # Dummy API keys
        self.gemini_key = "dummy_gemini_key"
        self.serpapi_key = "dummy_serpapi_key"
        
        # Test session ID
        self.session_id = "test_stage0_flow_session"
        
        # Paths
        self.backend_root = Path(__file__).parent.parent.parent
        self.results_dir = self.backend_root.parent / "results"
        self.expected_output_file = self.results_dir / f"stage_0_{self.session_id}.json"
        
        # Clean up any existing result file
        if self.expected_output_file.exists():
            os.remove(self.expected_output_file)

    def tearDown(self):
        # Clean up created result file
        if self.expected_output_file.exists():
            os.remove(self.expected_output_file)

    @patch('fact_checker.GeminiClient')
    @patch('fact_checker.MediaAnalyzer')
    @patch('fact_checker.ClaimExtractor')
    def test_stage0_results_persistence(self, MockClaimExtractor, MockMediaAnalyzer, MockGeminiClient):
        # Configure logging to see output
        import logging
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
        
        # Setup Mocks
        mock_gemini = MockGeminiClient.return_value
        
        mock_claim_extractor = MockClaimExtractor.return_value
        mock_claim_extractor.extract_claims.return_value = {"claims": [], "flagged_terms": []}
        
        mock_analyzer = MockMediaAnalyzer.return_value
        expected_media_analysis = {
            "repetition_detection": {"seen_before": True, "similarity_score": 0.99},
            "context_verification": {"matched_sources": [{"url": "http://example.com"}]}
        }
        mock_analyzer.analyze_media.return_value = expected_media_analysis
        
        # initialize checker
        checker = FactChecker(self.gemini_key, self.serpapi_key)
        
        # Create a session with an image to trigger Stage 0
        session_data = {
            "session_id": self.session_id,
            "entries": [
                {
                    "id": "entry_1", 
                    "text": "Extracted OCR Text", 
                    "image_id": "img_123", # Triggers has_images check
                    "source": "screen_capture"
                }
            ]
        }
        
        # Run pipeline
        checker.process_session(session_data)
        
        # Verification 1: File Exists
        self.assertTrue(self.expected_output_file.exists(), "Stage 0 result file was not created")
        
        # Verification 2: File Content
        with open(self.expected_output_file, 'r', encoding='utf-8') as f:
            saved_data = json.load(f)
            
        # Check if media_analysis is preserved
        self.assertEqual(saved_data.get('media_analysis'), expected_media_analysis)
        
        # Check if entries (OCR text) are preserved
        self.assertEqual(len(saved_data.get('entries', [])), 1)
        self.assertEqual(saved_data['entries'][0]['text'], "Extracted OCR Text")
        
        print(f"\nSUCCESS: Stage 0 results + OCR text correctly saved to {self.expected_output_file}")

if __name__ == '__main__':
    unittest.main()
