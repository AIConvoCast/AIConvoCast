#!/usr/bin/env python3
"""
Local version of the GitHub Actions Google credentials test.
This mimics the exact tests from .github/workflows/test-google-creds.yml
"""

import json
import os
import sys
from dotenv import load_dotenv

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')

def test_json_format():
    """Test JSON format - mimics the GitHub Actions step."""
    print("🔍 Testing JSON format...")
    
    if not os.path.exists('jmio-google-api.json'):
        print("❌ jmio-google-api.json not found!")
        return False
    
    try:
        with open('jmio-google-api.json', 'r') as f:
            creds = json.load(f)
        print('✅ JSON format is valid')
        print(f'Type: {creds.get("type", "Not found")}')
        print(f'Project ID: {creds.get("project_id", "Not found")}')
        print(f'Client Email: {creds.get("client_email", "Not found")}')
        return True
    except json.JSONDecodeError as e:
        print(f'❌ Invalid JSON: {e}')
        print('Content preview:')
        with open('jmio-google-api.json', 'r') as f:
            content = f.read()
            print(content[:300] + '...' if len(content) > 300 else content)
        return False
    except Exception as e:
        print(f'❌ Error reading file: {e}')
        return False

def test_required_fields():
    """Test required fields - mimics the GitHub Actions step."""
    print("🔍 Testing required fields...")
    
    try:
        with open('jmio-google-api.json', 'r') as f:
            creds = json.load(f)
        
        required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
        missing_fields = [field for field in required_fields if field not in creds]
        
        if missing_fields:
            print(f'❌ Missing required fields: {missing_fields}')
            return False
        else:
            print('✅ All required fields present')
            
        if creds.get('type') != 'service_account':
            print('❌ Not a service account credential')
            return False
        else:
            print('✅ Service account credential')
            return True
            
    except Exception as e:
        print(f'❌ Error testing required fields: {e}')
        return False

def test_google_authentication():
    """Test Google authentication - mimics the GitHub Actions step."""
    print("🔍 Testing Google authentication...")
    
    try:
        import gspread
        from google.oauth2 import service_account
        
        scopes = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        credentials = service_account.Credentials.from_service_account_file(
            'jmio-google-api.json', scopes=scopes
        )
        
        gc = gspread.authorize(credentials)
        print('✅ Successfully authenticated with Google')
        return True
        
    except ImportError as e:
        print(f'❌ Missing required package: {e}')
        print('Run: pip install gspread google-auth google-auth-oauthlib google-api-python-client')
        return False
    except Exception as e:
        print(f'❌ Authentication failed: {e}')
        return False

def test_google_sheets_access():
    """Test Google Sheets access - mimics the GitHub Actions step."""
    print("🔍 Testing Google Sheets access...")
    
    try:
        import gspread
        from google.oauth2 import service_account
        
        scopes = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        credentials = service_account.Credentials.from_service_account_file(
            'jmio-google-api.json', scopes=scopes
        )
        
        gc = gspread.authorize(credentials)
        
        # Try to list spreadsheets
        try:
            spreadsheets = gc.openall()
            print(f'✅ Can access {len(spreadsheets)} spreadsheets')
            
            # List first few spreadsheet names
            for i, sheet in enumerate(spreadsheets[:5]):
                print(f'  - {sheet.title}')
            if len(spreadsheets) > 5:
                print(f'  ... and {len(spreadsheets) - 5} more')
            return True
                
        except Exception as e:
            print(f'⚠️ Can authenticate but can\'t list spreadsheets: {e}')
            return False
            
    except Exception as e:
        print(f'❌ Google Sheets access failed: {e}')
        return False

def test_google_drive_access():
    """Test Google Drive access - mimics the GitHub Actions step."""
    print("🔍 Testing Google Drive access...")
    
    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
        
        scopes = ['https://www.googleapis.com/auth/drive']
        
        credentials = service_account.Credentials.from_service_account_file(
            'jmio-google-api.json', scopes=scopes
        )
        
        drive_service = build('drive', 'v3', credentials=credentials)
        
        # Try to list files
        try:
            results = drive_service.files().list(pageSize=10).execute()
            files = results.get('files', [])
            print(f'✅ Can access {len(files)} files in Google Drive')
            
            # List first few file names
            for i, file in enumerate(files[:5]):
                print(f'  - {file.get("name", "Unnamed")}')
            if len(files) > 5:
                print(f'  ... and {len(files) - 5} more')
            return True
                
        except Exception as e:
            print(f'⚠️ Can authenticate but can\'t list files: {e}')
            return False
            
    except ImportError as e:
        print(f'❌ Missing required package: {e}')
        print('Run: pip install google-api-python-client')
        return False
    except Exception as e:
        print(f'❌ Google Drive access failed: {e}')
        return False

def test_environment_variables():
    """Test environment variables - mimics GitHub Actions environment setup."""
    print("🔍 Testing Environment Variables...")
    
    load_dotenv()
    
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
            print(f"✅ {var}: {preview}")
        else:
            print(f"❌ {var}: Not set")
            all_good = False
    
    if not all_good:
        print("\n⚠️ Environment variable issues:")
        print("- Create a .env file with your API keys")
        print("- Or set the environment variables manually")
        print("- For GitHub Actions: Use repository secrets or environments")
    
    return all_good

def main():
    """Main function that runs all tests in order."""
    print("🚀 Local Google Credentials Test (GitHub Actions Style)")
    print("=" * 60)
    
    # Test environment variables first
    env_ok = test_environment_variables()
    
    # Check if credentials file exists
    if not os.path.exists('jmio-google-api.json'):
        print("\n❌ jmio-google-api.json not found!")
        print("Please ensure the file exists in the current directory.")
        sys.exit(1)
    
    # Run all tests in order (matching GitHub Actions workflow)
    tests = [
        ("Environment Variables", lambda: env_ok),  # Use the result from earlier
        ("JSON Format", test_json_format),
        ("Required Fields", test_required_fields),
        ("Google Authentication", test_google_authentication),
        ("Google Sheets Access", test_google_sheets_access),
        ("Google Drive Access", test_google_drive_access)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n--- {test_name} Test ---")
        result = test_func()
        results.append((test_name, result))
        if not result:
            print(f"❌ {test_name} test failed!")
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results Summary:")
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {test_name}")
        if result:
            passed += 1
    
    print(f"\nPassed: {passed}/{len(results)} tests")
    
    if passed == len(results):
        print("\n🎉 All tests passed! Your Google credentials are ready for GitHub Actions.")
        print("You can now run the main AI Podcast Pipeline workflow.")
    else:
        print(f"\n❌ {len(results) - passed} test(s) failed. Please fix the issues above.")
        print("Check the error messages for specific problems to resolve.")
    
    return passed == len(results)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 