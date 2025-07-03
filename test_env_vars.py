#!/usr/bin/env python3
"""
Simple script to test environment variables in GitHub Actions.
"""

import os
from dotenv import load_dotenv

def test_environment_variables():
    """Test if environment variables are properly set."""
    print("🔍 Testing Environment Variables in GitHub Actions...")
    
    # Load .env file if it exists
    load_dotenv()
    
    # Check each required variable
    required_vars = [
        'OPENAI_API_KEY',
        'ELEVENLABS_API_KEY',
        'SHARE_SHEET_WITH_EMAIL'
    ]
    
    all_good = True
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Show first few characters for verification
            preview = value[:10] + "..." if len(value) > 10 else value
            print(f"✅ {var}: {preview} (length: {len(value)})")
        else:
            print(f"❌ {var}: Not set")
            all_good = False
    
    # Check if we're in GitHub Actions
    if os.getenv('GITHUB_ACTIONS'):
        print(f"\n🔧 Running in GitHub Actions")
        print(f"   Workflow: {os.getenv('GITHUB_WORKFLOW', 'Unknown')}")
        print(f"   Run ID: {os.getenv('GITHUB_RUN_ID', 'Unknown')}")
        print(f"   Environment: {os.getenv('GITHUB_ENV', 'Not set')}")
    else:
        print(f"\n💻 Running locally")
    
    return all_good

if __name__ == "__main__":
    success = test_environment_variables()
    if success:
        print("\n🎉 All environment variables are properly configured!")
    else:
        print("\n❌ Some environment variables are missing!")
        print("Please check your GitHub environment configuration.")
    
    exit(0 if success else 1) 