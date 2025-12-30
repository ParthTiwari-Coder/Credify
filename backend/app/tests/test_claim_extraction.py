
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the class we are testing
from stages.claim_extractor import ClaimExtractor
from utils.gemini_client import GeminiClient

class TestClaimExtraction(unittest.TestCase):
    def setUp(self):
        # Mock Gemini Client
        self.mock_gemini = MagicMock(spec=GeminiClient)
        self.extractor = ClaimExtractor(self.mock_gemini)
        
        # Mock flag config (ClaimExtractor loads this in __init__)
        self.extractor.flag_config = {
            "TEST_FLAG": {"description": "test", "category": "test_cat"}
        }

    def test_combined_extraction(self):
        # Mock response from Gemini
        expected_response = {
            "claims": [
                {"claim": "Test Claim 1", "domain": "test", "source_entry_ids": ["e1"]}
            ],
            "flagged_terms": [
                {"term": "suspicious term", "flag_name": "TEST_FLAG", "entry_id": "e1"}
            ]
        }
        self.mock_gemini.extract_claims.return_value = expected_response
        
        # Test Input
        session_data = {
            "session_id": "test_session",
            "entries": [{"id": "e1", "text": "Test Claim 1 with suspicious term"}],
            "media_analysis": {}
        }
        
        # Run Extraction
        result = self.extractor.extract_claims(session_data)
        
        # Verify Calls
        self.mock_gemini.extract_claims.assert_called_once()
        call_args = self.mock_gemini.extract_claims.call_args
        self.assertEqual(call_args[0][0], session_data['entries'])
        self.assertEqual(call_args[0][1], session_data['media_analysis'])
        self.assertEqual(call_args[0][2], self.extractor.flag_config)
        
        # Verify Output Structure
        self.assertIn("claims", result)
        self.assertIn("flagged_terms", result)
        self.assertEqual(len(result["claims"]), 1)
        self.assertEqual(len(result["flagged_terms"]), 1)
        self.assertEqual(result["claims"][0]["claim"], "Test Claim 1")
        self.assertEqual(result["flagged_terms"][0]["flag_name"], "TEST_FLAG")
        
        print("\nSUCCESS: ClaimExtractor correctly verified combined extraction")

if __name__ == '__main__':
    unittest.main()
