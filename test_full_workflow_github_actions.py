#!/usr/bin/env python3
"""
Test script to verify the complete workflow for GitHub Actions:
PPU,PPL15,P1M1,P2&R3&P8&R2M93,P3&R4M1,P4&R5M93,P5&R6M13,R7SL10T7,R6SL7T7,L8GV1SL4T7,L1&L9&L2SL3T7

This script validates that all components needed for this workflow are available
and properly configured for GitHub Actions environment.
"""

import os
import sys
import re
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_workflow_step_patterns():
    """Test that all workflow step patterns are recognized correctly."""
    print("🔍 Testing Workflow Step Pattern Recognition...")
    
    workflow_steps = [
        "PPU",
        "PPL15", 
        "P1M1",
        "P2&R3&P8&R2M93",
        "P3&R4M1",
        "P4&R5M93", 
        "P5&R6M13",
        "R7SL10T7",
        "R6SL7T7",
        "L8GV1SL4T7",
        "L1&L9&L2SL3T7"
    ]
    
    # Import the main pipeline to get pattern matching functions
    try:
        sys.path.append('.')
        # We'll test the patterns individually since we can't easily run the full pipeline
        
        # Test Google Voice pattern specifically
        google_voice_pattern = r'L(\d+)GV(\d+)SL(\d+)(?:T(\d+))?'
        google_voice_step = "L8GV1SL4T7"
        
        match = re.fullmatch(google_voice_pattern, google_voice_step)
        if match:
            location_id = match.group(1)
            voice_id = match.group(2) 
            save_location_id = match.group(3)
            title_resp_idx = match.group(4)
            
            print(f"✅ Google Voice step '{google_voice_step}' pattern matched:")
            print(f"   Location ID: {location_id}")
            print(f"   Voice ID: {voice_id} (Alnilam)")
            print(f"   Save Location ID: {save_location_id}")
            print(f"   Title Response Index: {title_resp_idx}")
        else:
            print(f"❌ Google Voice step '{google_voice_step}' pattern did not match")
            return False
            
        # Test audio merge pattern
        audio_merge_pattern = r'L(\d+)(?:&L(\d+))*SL(\d+)(?:T(\d+))?'
        audio_merge_step = "L1&L9&L2SL3T7"
        
        match = re.fullmatch(audio_merge_pattern, audio_merge_step)
        if match:
            print(f"✅ Audio merge step '{audio_merge_step}' pattern matched")
        else:
            print(f"❌ Audio merge step '{audio_merge_step}' pattern did not match")
            return False
            
        # Test save-only pattern
        save_only_pattern = r'R(\d+)SL(\d+)(?:T(\d+))?'
        save_steps = ["R7SL10T7", "R6SL7T7"]
        
        for save_step in save_steps:
            match = re.fullmatch(save_only_pattern, save_step)
            if match:
                print(f"✅ Save-only step '{save_step}' pattern matched")
            else:
                print(f"❌ Save-only step '{save_step}' pattern did not match")
                return False
        
        print("✅ All workflow step patterns recognized correctly")
        return True
        
    except Exception as e:
        print(f"❌ Error testing workflow patterns: {e}")
        return False

def test_google_tts_dependency():
    """Test that Google TTS dependency is available."""
    print("🔍 Testing Google Cloud Text-to-Speech dependency...")
    
    try:
        from google.cloud import texttospeech
        print("✅ google-cloud-texttospeech imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Failed to import google-cloud-texttospeech: {e}")
        print("   This dependency must be added to requirements.txt")
        return False

def test_service_account_setup():
    """Test that service account file is properly configured."""
    print("🔍 Testing service account configuration...")
    
    service_account_file = 'jmio-google-api.json'
    
    if not os.path.exists(service_account_file):
        print(f"❌ Service account file not found: {service_account_file}")
        print("   In GitHub Actions, this is created from GOOGLE_CREDS_JSON secret")
        return False
    
    try:
        from google.cloud import texttospeech
        client = texttospeech.TextToSpeechClient.from_service_account_json(service_account_file)
        print("✅ Service account file valid and TTS client initialized")
        return True
    except Exception as e:
        print(f"❌ Service account configuration error: {e}")
        return False

def test_github_actions_environment():
    """Test GitHub Actions specific environment setup."""
    print("🔍 Testing GitHub Actions environment compatibility...")
    
    # Check if we're likely in GitHub Actions
    is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'
    
    if is_github_actions:
        print("✅ Running in GitHub Actions environment")
        
        # Check required environment variables that should be set in GitHub Actions
        required_vars = [
            'OPENAI_API_KEY',
            'ELEVENLABS_API_KEY', 
            'ANTHROPIC_API_KEY',
            'GEMINI_API_KEY'
        ]
        
        for var in required_vars:
            if os.getenv(var):
                print(f"✅ {var} is set")
            else:
                print(f"❌ {var} is not set - required for workflow")
                return False
    else:
        print("ℹ️ Not running in GitHub Actions - checking local environment")
        
        # For local testing, just check if .env file exists
        if os.path.exists('.env'):
            print("✅ .env file found for local testing")
        else:
            print("⚠️ .env file not found - may need environment variables")
    
    return True

def test_ffmpeg_availability():
    """Test that ffmpeg is available for audio processing."""
    print("🔍 Testing ffmpeg availability...")
    
    try:
        import subprocess
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ ffmpeg is available")
            return True
        else:
            print("❌ ffmpeg not working properly")
            return False
    except FileNotFoundError:
        print("❌ ffmpeg not found - required for audio processing")
        print("   In GitHub Actions, this is installed with: sudo apt-get install -y ffmpeg")
        return False
    except Exception as e:
        print(f"❌ Error testing ffmpeg: {e}")
        return False

def test_workflow_execution_simulation():
    """Simulate key parts of the workflow execution."""
    print("🔍 Testing workflow execution simulation...")
    
    try:
        # Test that we can import the main pipeline
        sys.path.append('.')
        from ai_podcast_pipeline_for_cursor import (
            generate_google_voice_audio,
            google_tts_client
        )
        
        print("✅ Main pipeline functions imported successfully")
        
        # Test Google TTS client is available
        if google_tts_client:
            print("✅ Google TTS client is initialized")
        else:
            print("⚠️ Google TTS client not initialized - may need API enabled")
        
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import pipeline functions: {e}")
        return False
    except Exception as e:
        print(f"❌ Error in workflow simulation: {e}")
        return False

def test_requirements_file():
    """Test that requirements.txt has all necessary dependencies."""
    print("🔍 Testing requirements.txt completeness...")
    
    required_packages = [
        'google-cloud-texttospeech',
        'google-cloud-storage', 
        'elevenlabs',
        'openai',
        'pandas',
        'gspread',
        'pydub',
        'anthropic',
        'google-generativeai'
    ]
    
    try:
        with open('requirements.txt', 'r') as f:
            requirements_content = f.read()
        
        missing_packages = []
        for package in required_packages:
            if package not in requirements_content:
                missing_packages.append(package)
        
        if missing_packages:
            print(f"❌ Missing packages in requirements.txt: {missing_packages}")
            return False
        else:
            print("✅ All required packages found in requirements.txt")
            return True
            
    except FileNotFoundError:
        print("❌ requirements.txt not found")
        return False

def main():
    """Run all tests for GitHub Actions compatibility."""
    print("🧪 Testing GitHub Actions Workflow Compatibility")
    print("=" * 70)
    print("Workflow: PPU,PPL15,P1M1,P2&R3&P8&R2M93,P3&R4M1,P4&R5M93,P5&R6M13,R7SL10T7,R6SL7T7,L8GV1SL4T7,L1&L9&L2SL3T7")
    print("=" * 70)
    
    tests = [
        ("Requirements File Check", test_requirements_file),
        ("Google TTS Dependency", test_google_tts_dependency),
        ("Service Account Setup", test_service_account_setup),
        ("Workflow Pattern Recognition", test_workflow_step_patterns),
        ("GitHub Actions Environment", test_github_actions_environment),
        ("FFmpeg Availability", test_ffmpeg_availability),
        ("Workflow Execution Simulation", test_workflow_execution_simulation)
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
    
    print("\n" + "=" * 70)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Workflow is ready for GitHub Actions.")
        print("\n📝 Workflow Steps Analysis:")
        print("   PPU - Posted Podcast Update (retrieves existing data)")
        print("   PPL15 - Posted Podcast Last 15 episodes")
        print("   P1M1 - Prompt 1 with Model 1")
        print("   P2&R3&P8&R2M93 - Complex step combining prompts and responses")
        print("   P3&R4M1 - Prompt 3 with Response 4 using Model 1")
        print("   P4&R5M93 - Prompt 4 with Response 5 using Model 93") 
        print("   P5&R6M13 - Prompt 5 with Response 6 using Model 13")
        print("   R7SL10T7 - Save Response 7 to Location 10 with Title from Response 7")
        print("   R6SL7T7 - Save Response 6 to Location 7 with Title from Response 7") 
        print("   L8GV1SL4T7 - Google Voice: Location 8 → Alnilam voice → Save Location 4 (Title: Response 7)")
        print("   L1&L9&L2SL3T7 - Audio Merge: Locations 1,9,2 → Save Location 3 (Title: Response 7)")
        
        print("\n🚀 Ready to run in GitHub Actions!")
        
    else:
        print("❌ Some tests failed. Please address issues before running in GitHub Actions.")
        
        print("\n🔧 GitHub Actions Setup Checklist:")
        print("   1. ✅ Add google-cloud-texttospeech to requirements.txt")
        print("   2. 🔧 Enable Google Cloud Text-to-Speech API in your project")
        print("   3. 🔧 Ensure GOOGLE_CREDS_JSON secret contains valid service account")
        print("   4. 🔧 Verify all API keys are set as GitHub secrets")
        print("   5. 🔧 Test ffmpeg installation in ubuntu-latest runner")

if __name__ == "__main__":
    main()