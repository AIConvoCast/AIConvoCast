#!/usr/bin/env python3
"""
Test script for Google Cloud Text-to-Speech integration with Chirp 3 HD voices.
This script tests the new Google Voice functionality added to the AI podcast pipeline.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_google_voice_import():
    """Test if Google TTS can be imported and initialized."""
    try:
        from google.cloud import texttospeech
        print("✅ Google Cloud Text-to-Speech library imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Failed to import Google Cloud Text-to-Speech: {e}")
        print("   Please install: pip install google-cloud-texttospeech")
        return False

def test_google_voice_client():
    """Test if Google TTS client can be initialized."""
    try:
        from google.cloud import texttospeech
        service_account_file = 'jmio-google-api.json'
        
        if not os.path.exists(service_account_file):
            print(f"❌ Service account file not found: {service_account_file}")
            return False
            
        client = texttospeech.TextToSpeechClient.from_service_account_json(service_account_file)
        print("✅ Google TTS client initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to initialize Google TTS client: {e}")
        return False

def test_google_voice_generation():
    """Test Google Voice audio generation with Alnilam voice."""
    try:
        # Import the function from our pipeline
        sys.path.append('.')
        from ai_podcast_pipeline_for_cursor import generate_google_voice_audio, MP3_OUTPUT_DIR
        
        # Test text
        test_text = "Hello! This is a test of the Google Cloud Text-to-Speech integration using the Alnilam voice from Chirp 3 HD. The voice should sound natural and engaging."
        
        # Output path
        output_path = MP3_OUTPUT_DIR / "test_google_voice_alnilam.mp3"
        
        print(f"🎤 Testing Google Voice generation with text: '{test_text[:50]}...'")
        print(f"   Using voice: Alnilam")
        print(f"   Output path: {output_path}")
        
        # Generate audio
        result = generate_google_voice_audio(test_text, "Alnilam", output_path)
        
        if result and os.path.exists(result):
            file_size = os.path.getsize(result)
            print(f"✅ Google Voice generation successful!")
            print(f"   Audio saved as: {result}")
            print(f"   File size: {file_size} bytes")
            return True
        else:
            print("❌ Google Voice generation failed - no output file created")
            return False
            
    except Exception as e:
        print(f"❌ Google Voice generation error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_other_google_voices():
    """Test a few other Google Chirp 3 HD voices."""
    try:
        sys.path.append('.')
        from ai_podcast_pipeline_for_cursor import generate_google_voice_audio, MP3_OUTPUT_DIR
        
        test_voices = [
            ("Achernar", "Female voice test"),
            ("Charon", "Male voice test"),
            ("Kore", "Another female voice test")
        ]
        
        for voice_name, test_text in test_voices:
            output_path = MP3_OUTPUT_DIR / f"test_google_voice_{voice_name.lower()}.mp3"
            
            print(f"🎤 Testing {voice_name} voice...")
            result = generate_google_voice_audio(test_text, voice_name, output_path)
            
            if result and os.path.exists(result):
                file_size = os.path.getsize(result)
                print(f"✅ {voice_name} voice test successful! ({file_size} bytes)")
            else:
                print(f"❌ {voice_name} voice test failed")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Multiple voice test error: {e}")
        return False

def test_workflow_pattern():
    """Test that the GV1 workflow pattern is recognized."""
    try:
        import re
        
        # Test the regex pattern from the workflow
        pattern = r'L(\d+)GV(\d+)SL(\d+)(?:T(\d+))?'
        
        test_cases = [
            "L8GV1SL4",      # Basic pattern: Location 8, Google Voice 1, Save Location 4
            "L8GV1SL4T2",    # With title: Location 8, Google Voice 1, Save Location 4, Title from response 2
            "L10GV2SL5",     # Different voice and locations
            "L8GV1SL4T10"    # With higher title index
        ]
        
        for test_case in test_cases:
            match = re.fullmatch(pattern, test_case)
            if match:
                location_id = match.group(1)
                voice_id = match.group(2)
                save_location_id = match.group(3)
                title_resp_idx = match.group(4)
                
                print(f"✅ Pattern '{test_case}' matched:")
                print(f"   Location ID: {location_id}")
                print(f"   Voice ID: {voice_id}")
                print(f"   Save Location ID: {save_location_id}")
                print(f"   Title Response Index: {title_resp_idx}")
            else:
                print(f"❌ Pattern '{test_case}' did not match")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Workflow pattern test error: {e}")
        return False

def main():
    """Run all tests."""
    print("🧪 Testing Google Cloud Text-to-Speech Integration")
    print("=" * 60)
    
    tests = [
        ("Import Test", test_google_voice_import),
        ("Client Initialization", test_google_voice_client),
        ("Workflow Pattern Recognition", test_workflow_pattern),
        ("Alnilam Voice Generation", test_google_voice_generation),
        ("Multiple Voices Test", test_other_google_voices)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 Running {test_name}...")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} ERROR: {e}")
    
    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Google Voice integration is working correctly.")
        print("\n📝 Usage Instructions:")
        print("   To use Google Voice in your workflow, use the pattern: L8GV1SL4")
        print("   Where:")
        print("   - L8 = Source location ID 8 (where to get the text file)")
        print("   - GV1 = Google Voice ID 1 (Alnilam)")
        print("   - SL4 = Save location ID 4 (where to save the audio)")
        print("   - Optional: T2 = Use response 2 as the title")
        print("\n🎙️ Available Google Voices:")
        print("   GV1 = Alnilam (Male)")
        print("   GV2 = Achernar (Female)")
        print("   GV3 = Achird (Male)")
        print("   GV4 = Algenib (Male)")
        print("   GV5 = Algieba (Male)")
        print("   GV6 = Aoede (Female)")
        print("   GV7 = Autonoe (Female)")
        print("   GV8 = Callirrhoe (Female)")
        print("   GV9 = Charon (Male)")
        print("   GV10 = Despina (Female)")
        print("   ... and more (up to GV30)")
    else:
        print("❌ Some tests failed. Please check the configuration.")
        
        print("\n🔧 Troubleshooting:")
        print("   1. Ensure 'jmio-google-api.json' service account file exists")
        print("   2. Install Google Cloud TTS: pip install google-cloud-texttospeech")
        print("   3. Verify service account has Text-to-Speech API permissions")
        print("   4. Check that Google Cloud Text-to-Speech API is enabled")

if __name__ == "__main__":
    main()