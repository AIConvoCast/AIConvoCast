#!/usr/bin/env python3
"""
Test script for Eleven Labs integration
"""

import os
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')

def test_eleven_labs_connection():
    """Test basic Eleven Labs API connection using official client"""
    if not ELEVENLABS_API_KEY:
        print("❌ ELEVENLABS_API_KEY not found in .env file")
        return False
    
    try:
        from elevenlabs.client import ElevenLabs
        
        # Initialize the client
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        
        # Test API connection by listing voices
        voices_response = client.voices.get_all()
        voices = voices_response.voices  # Get the actual voices list
        
        print(f"✅ Eleven Labs API connection successful!")
        print(f"   Found {len(voices)} voices")
        
        # Print available voices
        print("\nAvailable voices:")
        for voice in voices[:5]:  # Show first 5
            print(f"   - {voice.name} (ID: {voice.voice_id})")
        
        return True
        
    except ImportError:
        print("⚠️ ElevenLabs Python client not installed. Testing with REST API...")
        return test_eleven_labs_connection_rest()
    except Exception as e:
        print(f"❌ Eleven Labs API connection failed: {e}")
        return False

def test_eleven_labs_connection_rest():
    """Fallback REST API test"""
    url = "https://api.elevenlabs.io/v1/voices"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            voices = response.json()
            print(f"✅ Eleven Labs REST API connection successful!")
            print(f"   Found {len(voices.get('voices', []))} voices")
            
            # Print available voices
            print("\nAvailable voices:")
            for voice in voices.get('voices', [])[:5]:  # Show first 5
                print(f"   - {voice.get('name', 'Unknown')} (ID: {voice.get('voice_id', 'Unknown')})")
            
            return True
        else:
            print(f"❌ Eleven Labs REST API error: {response.status_code} {response.text}")
            return False
    except Exception as e:
        print(f"❌ Eleven Labs REST API connection failed: {e}")
        return False

def test_voice_generation():
    """Test voice generation with sample text using official client"""
    if not ELEVENLABS_API_KEY:
        print("❌ ELEVENLABS_API_KEY not found in .env file")
        return False
    
    # Sample text to convert
    test_text = "Hello! This is a test of the Eleven Labs text-to-speech integration."
    
    # Liam voice ID
    voice_id = "TX3LPaxmHKxFdv7VOQHJ"
    
    try:
        from elevenlabs.client import ElevenLabs
        
        # Initialize the client
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        
        print(f"🎤 Testing voice generation with text: '{test_text}'")
        print(f"   Using voice ID: {voice_id}")
        
        # Generate audio with custom settings (returns a generator)
        # Note: v3 requires stability to be exactly 0.0, 0.5, or 1.0
        audio_stream = client.text_to_speech.convert(
            text=test_text,
            voice_id=voice_id,
            voice_settings={
                "stability": 0.5,  # v3: 0.0=Creative, 0.5=Natural, 1.0=Robust
                "similarity_boost": 0.7,
                "style": 0.5,
                "speed": 1.06
            },
            model_id="eleven_v3"
        )
        
        # Save the audio file
        with open("test_output.mp3", "wb") as f:
            for chunk in audio_stream:
                f.write(chunk)
        
        print(f"✅ Voice generation successful! Audio saved as 'test_output.mp3'")
        return True
        
    except ImportError:
        print("⚠️ ElevenLabs Python client not installed. Testing with REST API...")
        return test_voice_generation_rest()
    except Exception as e:
        print(f"❌ Voice generation error: {e}")
        return False

def test_voice_generation_rest():
    """Fallback REST API voice generation test"""
    test_text = "Hello! This is a test of the Eleven Labs text-to-speech integration."
    voice_id = "TX3LPaxmHKxFdv7VOQHJ"
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "text": test_text,
        "model_id": "eleven_v3",
        "voice_settings": {
            "stability": 0.5,  # v3: 0.0=Creative, 0.5=Natural, 1.0=Robust
            "similarity_boost": 0.7,
            "style": 0.5,
            "speed": 1.06
        }
    }
    
    try:
        print(f"🎤 Testing voice generation with REST API...")
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            # Save the audio file
            with open("test_output.mp3", "wb") as f:
                f.write(response.content)
            print(f"✅ Voice generation successful! Audio saved as 'test_output.mp3'")
            return True
        else:
            print(f"❌ Voice generation failed: {response.status_code} {response.text}")
            return False
    except Exception as e:
        print(f"❌ Voice generation error: {e}")
        return False

def test_specific_chunk():
    """Test voice generation with a user-supplied chunk using official client"""
    if not ELEVENLABS_API_KEY:
        print("❌ ELEVENLABS_API_KEY not found in .env file")
        return False

    # Paste your chunk here for testing:
    test_chunk = """Today we will be diving into exciting developments shaping the future of AI across education, startup innovation, and corporate culture. We'll explore Google's new Gemini AI Suite that's transforming classrooms, the massive funding secured by Thinking Machines Lab, and Microsoft's bold push for AI proficiency among its employees. So let's get started!"""

    # Liam voice ID
    voice_id = "TX3LPaxmHKxFdv7VOQHJ"

    try:
        from elevenlabs.client import ElevenLabs

        # Initialize the client
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

        print(f"🎤 Testing voice generation with user chunk: (length: {len(test_chunk)})")
        print(f"   Using voice ID: {voice_id}")

        # Generate audio with custom settings (returns a generator)
        # Note: v3 requires stability to be exactly 0.0, 0.5, or 1.0
        audio_stream = client.text_to_speech.convert(
            text=test_chunk,
            voice_id=voice_id,
            voice_settings={
                "stability": 0.5,  # v3: 0.0=Creative, 0.5=Natural, 1.0=Robust
                "similarity_boost": 0.7,
                "style": 0.5,
                "speed": 1.06
            },
            model_id="eleven_v3"
        )

        # Save the audio file
        with open("test_chunk_output.mp3", "wb") as f:
            for chunk in audio_stream:
                f.write(chunk)

        print(f"✅ Voice generation successful! Audio saved as 'test_chunk_output.mp3'")
        return True

    except ImportError:
        print("⚠️ ElevenLabs Python client not installed. Testing with REST API...")
        return test_voice_generation_rest()
    except Exception as e:
        print(f"❌ Voice generation error: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Eleven Labs Integration")
    print("=" * 40)
    
    # Test 1: API Connection
    print("\n1. Testing API Connection...")
    connection_ok = test_eleven_labs_connection()
    
    # Test 2: Voice Generation (only if connection works)
    if connection_ok:
        print("\n2. Testing Voice Generation...")
        print("   Using Liam voice ID: TX3LPaxmHKxFdv7VOQHJ")
        generation_ok = test_voice_generation()
    else:
        print("\n2. Skipping voice generation test due to connection failure")
        generation_ok = False
    
    # Test 3: Specific Chunk Test
    print("\n3. Testing Specific Chunk (paste your chunk in test_specific_chunk)...")
    test_specific_chunk()
    
    # Summary
    print("\n" + "=" * 40)
    print("Test Summary:")
    print(f"   API Connection: {'✅ PASS' if connection_ok else '❌ FAIL'}")
    print(f"   Voice Generation: {'✅ PASS' if generation_ok else '❌ FAIL'}")
    print("   Specific Chunk: See above for result.")
    
    if connection_ok and generation_ok:
        print("\n🎉 All tests passed! Eleven Labs integration is working correctly.")
        print("   You can now run the main pipeline with L8E1SL4 workflow steps.")
    else:
        print("\n⚠️  Some tests failed. Please check your configuration.")
        print("   - Ensure ELEVENLABS_API_KEY is set in .env file")
        print("   - Verify your API key is valid")
        print("   - Install elevenlabs package: pip install elevenlabs") 