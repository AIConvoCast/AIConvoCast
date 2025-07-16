#!/usr/bin/env python3
"""
Debug script to check what's wrong with Google credentials JSON.
Run this locally to test your JSON before updating GitHub secrets.
"""

import json
import os

def debug_json_file():
    """Debug the local JSON file."""
    print("🔍 Debugging local jmio-google-api.json file...")
    
    if not os.path.exists('jmio-google-api.json'):
        print("❌ jmio-google-api.json not found!")
        return
    
    try:
        with open('jmio-google-api.json', 'r') as f:
            content = f.read()
        
        print(f"📏 File size: {len(content)} characters")
        print(f"📄 First 100 characters: {repr(content[:100])}")
        print(f"📄 Last 100 characters: {repr(content[-100:])}")
        
        # Check for common issues
        if content.startswith('"') and content.endswith('"'):
            print("⚠️ JSON appears to be wrapped in quotes - this is wrong!")
            print("   Remove the outer quotes from the GitHub secret")
        
        if content.count('{') != content.count('}'):
            print("⚠️ Mismatched braces detected!")
            print(f"   Opening braces: {content.count('{')}")
            print(f"   Closing braces: {content.count('}')}")
        
        # Try to parse
        try:
            creds = json.loads(content)
            print("✅ JSON parses successfully!")
            print(f"   Type: {creds.get('type', 'Not found')}")
            print(f"   Project ID: {creds.get('project_id', 'Not found')}")
            print(f"   Client Email: {creds.get('client_email', 'Not found')}")
        except json.JSONDecodeError as e:
            print(f"❌ JSON parse error: {e}")
            print(f"   Error at line {e.lineno}, column {e.colno}")
            
            # Show the problematic area
            lines = content.split('\n')
            if e.lineno <= len(lines):
                line = lines[e.lineno - 1]
                print(f"   Problematic line: {repr(line)}")
                if e.colno <= len(line):
                    print(f"   Problem at position: {line[:e.colno]}|{line[e.colno:]}")
        
    except Exception as e:
        print(f"❌ Error reading file: {e}")

def create_correct_secret_format():
    """Show how the secret should be formatted."""
    print("\n📋 How to format the GitHub secret:")
    print("1. Open jmio-google-api.json in a text editor")
    print("2. Select ALL content (Ctrl+A)")
    print("3. Copy (Ctrl+C)")
    print("4. In GitHub:")
    print("   - Go to Settings → Secrets → Actions")
    print("   - Edit GOOGLE_CREDS_JSON")
    print("   - Delete current content")
    print("   - Paste the JSON (no extra quotes)")
    print("   - Click Update secret")
    print("\n⚠️ Common mistakes:")
    print("   - Don't add quotes around the JSON")
    print("   - Don't add extra spaces or newlines")
    print("   - Make sure the JSON is complete")

if __name__ == "__main__":
    debug_json_file()
    create_correct_secret_format() 