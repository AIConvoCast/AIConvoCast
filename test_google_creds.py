#!/usr/bin/env python3
"""
Test script to verify Google credentials are working correctly.
Run this locally before pushing to GitHub Actions.
"""

import json
import os
from dotenv import load_dotenv

def test_google_credentials():
    """Test Google credentials from local file."""
    print("🔍 Testing Google Credentials...")
    
    # Test 1: Check if file exists
    creds_file = 'jmio-google-api.json'
    if not os.path.exists(creds_file):
        print(f"❌ {creds_file} not found!")
        return False
    
    print(f"✅ {creds_file} found")
    
    # Test 2: Check if file is valid JSON
    try:
        with open(creds_file, 'r') as f:
            creds = json.load(f)
        print("✅ JSON is valid")
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        return False
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return False
    
    # Test 3: Check required fields
    required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
    missing_fields = []
    
    for field in required_fields:
        if field not in creds:
            missing_fields.append(field)
        else:
            print(f"✅ {field}: {creds[field][:20]}{'...' if len(str(creds[field])) > 20 else ''}")
    
    if missing_fields:
        print(f"❌ Missing required fields: {missing_fields}")
        return False
    
    # Test 4: Check if it's a service account
    if creds.get('type') != 'service_account':
        print("❌ Not a service account credential")
        return False
    
    print("✅ Service account credential")
    
    # Test 5: Try to connect to Google Sheets
    try:
        import gspread
        from google.oauth2 import service_account
        
        scopes = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        credentials = service_account.Credentials.from_service_account_file(
            creds_file, scopes=scopes
        )
        
        gc = gspread.authorize(credentials)
        print("✅ Successfully authenticated with Google")
        
        # Test 6: Try to list spreadsheets (optional)
        try:
            spreadsheets = gc.openall()
            print(f"✅ Can access {len(spreadsheets)} spreadsheets")
        except Exception as e:
            print(f"⚠️ Can authenticate but can't list spreadsheets: {e}")
        
        return True
        
    except ImportError as e:
        print(f"❌ Missing required package: {e}")
        print("Run: pip install gspread google-auth google-auth-oauthlib")
        return False
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return False

def test_environment_variables():
    """Test environment variables."""
    print("\n🔍 Testing Environment Variables...")
    
    load_dotenv()
    
    vars_to_check = [
        'OPENAI_API_KEY',
        'ELEVENLABS_API_KEY',
        'SHARE_SHEET_WITH_EMAIL'
    ]
    
    all_good = True
    for var in vars_to_check:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {value[:10]}{'...' if len(value) > 10 else ''}")
        else:
            print(f"❌ {var}: Not set")
            all_good = False
    
    return all_good

def main():
    """Main test function."""
    print("🚀 Google Credentials Test Script")
    print("=" * 40)
    
    # Test Google credentials
    google_ok = test_google_credentials()
    
    # Test environment variables
    env_ok = test_environment_variables()
    
    print("\n" + "=" * 40)
    if google_ok and env_ok:
        print("🎉 All tests passed! Your setup is ready for GitHub Actions.")
        print("\nNext steps:")
        print("1. Copy the ENTIRE content of jmio-google-api.json")
        print("2. Update the GOOGLE_CREDS_JSON secret in GitHub")
        print("3. Run the 'Test Setup' workflow in GitHub Actions")
    else:
        print("❌ Some tests failed. Please fix the issues above.")
        if not google_ok:
            print("\nGoogle credentials issues:")
            print("- Check that jmio-google-api.json exists and is valid JSON")
            print("- Verify it's a service account credential")
            print("- Ensure it has the correct permissions")
        if not env_ok:
            print("\nEnvironment variable issues:")
            print("- Create a .env file with your API keys")
            print("- Or set the environment variables manually")

if __name__ == "__main__":
    main() 