"""
Test script for fact-checking system
Demonstrates the 5-stage pipeline with sample data
"""

import json
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import fact checker
import fact_checker
from fact_checker import FactChecker


def test_fact_checker():
    """Test the fact-checking system with sample session data"""
    
    # Check for API key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ ERROR: GEMINI_API_KEY environment variable not set")
        print("Please set it with: export GEMINI_API_KEY='your-api-key'")
        return
    
    print("=" * 80)
    print("FACT-CHECKING SYSTEM TEST")
    print("=" * 80)
    
    # Initialize fact-checker
    print("\n📦 Initializing fact-checking system...")
    checker = FactChecker(api_key)
    print("✅ System initialized\n")
    
    # Sample session data with various claims
    sample_session = {
        "session_id": "test_session_001",
        "type": "combined_session",
        "start_time": "2025-12-26T17:00:00.000Z",
        "entries": [
            {
                "id": "entry_1",
                "text": "Drinking hot water cures COVID-19",
                "source": "subtitle",
                "timestamp": "00:00:15"
            },
            {
                "id": "entry_2",
                "text": "I think this is amazing!",
                "source": "subtitle",
                "timestamp": "00:00:30"
            },
            {
                "id": "entry_3",
                "text": "The Earth orbits around the Sun",
                "source": "subtitle",
                "timestamp": "00:01:00"
            },
            {
                "id": "entry_4",
                "text": "Scientists have proven that vaccines are 100% safe and effective",
                "source": "subtitle",
                "timestamp": "00:01:30"
            }
        ],
        "media_metadata": {
            "platform": "YouTube",
            "media_type": "video"
        }
    }
    
    print("📄 Sample Session Data:")
    print(json.dumps(sample_session, indent=2))
    print("\n" + "=" * 80)
    
    # Process session
    print("\n🔍 Processing session through 5-stage pipeline...\n")
    result = checker.process_session(sample_session)
    
    # Display results
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    
    print(f"\nSession ID: {result['session_id']}")
    print(f"Status: {result['status']}")
    print(f"Total Claims: {result['total_claims']}")
    
    if result['total_claims'] > 0:
        print("\n" + "-" * 80)
        for i, claim in enumerate(result['claims'], 1):
            print(f"\nCLAIM {i}:")
            print(f"  Text: {claim['claim']}")
            print(f"  Verdict: {claim['verdict']}")
            print(f"  Trust Score: {claim['trust_score']}/100")
            print(f"  Flags: {', '.join(claim['flags']) if claim['flags'] else 'None'}")
            print(f"  Domain: {claim['metadata']['domain']}")
            print(f"\n  Explanation:")
            for line in claim['explanation'].split('\n'):
                if line.strip():
                    print(f"    {line}")
            print("-" * 80)
    
    # Save results
    output_file = Path(__file__).parent.parent / "sessions" / "fact_check_test_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Results saved to: {output_file}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    test_fact_checker()
