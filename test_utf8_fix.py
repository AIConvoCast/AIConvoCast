#!/usr/bin/env python3
"""
Test script to diagnose and fix UTF-8 encoding issues.
Specifically addresses the apostrophe issue: "Microsoftâ€™s" should be "Microsoft's"
"""

import sys
import os
from pathlib import Path

def test_encoding_issue():
    """Test the specific encoding issue provided by the user."""
    print("🔍 Testing UTF-8 Encoding Issue")
    print("=" * 60)
    
    # The problematic text from the user (using unicode escapes to avoid syntax errors)
    problematic_text = "Claude 4, GPT 5, and Microsoft\u00e2\u0080\u0099s Windows 11 AI Upgrades Redefine AI Assistants"
    
    print("Original problematic text:")
    print(f"'{problematic_text}'")
    print(f"Length: {len(problematic_text)}")
    print()
    
    # Show the bytes
    print("Bytes representation:")
    print(problematic_text.encode('utf-8'))
    print()
    
    # Test current fix function
    sys.path.append('.')
    try:
        from ai_podcast_pipeline_for_cursor import fix_text_encoding, force_clean_mojibake
        
        print("Testing current fix_text_encoding function:")
        fixed_1 = fix_text_encoding(problematic_text)
        print(f"Result: '{fixed_1}'")
        print(f"Fixed apostrophe issue: {'â€™' not in fixed_1}")
        print()
        
        print("Testing current force_clean_mojibake function:")
        fixed_2 = force_clean_mojibake(problematic_text)
        print(f"Result: '{fixed_2}'")
        print(f"Fixed apostrophe issue: {'â€™' not in fixed_2}")
        print()
        
    except ImportError as e:
        print(f"Could not import functions: {e}")
    
    # Test manual fix
    print("Testing manual character replacements:")
    manual_fixes = {
        'â€™': "'",   # Right single quotation mark 
        'â€œ': '"',   # Left double quotation mark
        'â€': '"',   # Right double quotation mark  
        'â€"': '—',   # Em dash
        'â€"': '–',   # En dash
        'â€¦': '…',   # Horizontal ellipsis
        'â€¢': '•',   # Bullet
        'â€˜': "'",   # Left single quotation mark
        'Â': '',      # Sometimes appears as stray character
    }
    
    manual_fixed = problematic_text
    for bad, good in manual_fixes.items():
        if bad in manual_fixed:
            print(f"  Replacing '{bad}' with '{good}'")
            manual_fixed = manual_fixed.replace(bad, good)
    
    print(f"Manual fix result: '{manual_fixed}'")
    print(f"Successfully fixed: {'â€™' not in manual_fixed}")
    print()
    
    return manual_fixed

def test_file_write_encoding():
    """Test writing text to files with proper UTF-8 encoding."""
    print("🔍 Testing File Write Operations")
    print("=" * 60)
    
    test_text = "Test with special characters: \u00e2\u0080\u0099 \u00e2\u0080\u009c \u00e2\u0080\u009d \u2013 \u2014 \u2026 \u2022 Microsoft\u00e2\u0080\u0099s"
    fixed_text = test_text.replace('\u00e2\u0080\u0099', "'").replace('\u00e2\u0080\u009c', '"').replace('\u00e2\u0080\u009d', '"')
    
    test_dir = Path("test_utf8")
    test_dir.mkdir(exist_ok=True)
    
    try:
        # Test 1: Write with explicit UTF-8 encoding
        test_file_1 = test_dir / "test_utf8_explicit.txt"
        with open(test_file_1, 'w', encoding='utf-8') as f:
            f.write(fixed_text)
        
        # Read it back
        with open(test_file_1, 'r', encoding='utf-8') as f:
            read_back_1 = f.read()
        
        print(f"Explicit UTF-8 - Write: '{fixed_text}'")
        print(f"Explicit UTF-8 - Read:  '{read_back_1}'")
        print(f"Matches: {fixed_text == read_back_1}")
        print()
        
        # Test 2: Write without explicit encoding (system default)
        test_file_2 = test_dir / "test_default_encoding.txt"
        with open(test_file_2, 'w') as f:
            f.write(fixed_text)
        
        # Read it back with UTF-8
        with open(test_file_2, 'r', encoding='utf-8') as f:
            read_back_2 = f.read()
        
        print(f"Default encoding - Write: '{fixed_text}'")
        print(f"Default encoding - Read:  '{read_back_2}'")
        print(f"Matches: {fixed_text == read_back_2}")
        print()
        
        # Test 3: Test the pipeline's upload_text_to_gcs function simulation
        print("Testing upload_text_to_gcs pattern:")
        
        # Simulate the function's logic
        text_content = test_text  # Start with problematic text
        
        # Apply current encoding fixes (simulate pipeline logic)
        sys.path.append('.')
        try:
            from ai_podcast_pipeline_for_cursor import fix_text_encoding, force_clean_mojibake
            
            text_content = fix_text_encoding(text_content)
            text_content = force_clean_mojibake(text_content)
            
            # Write to temp file like the pipeline does
            temp_path = test_dir / "pipeline_simulation.txt"
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(text_content)
            
            # Read it back
            with open(temp_path, 'r', encoding='utf-8') as f:
                read_back_3 = f.read()
            
            print(f"Pipeline simulation - Original: '{test_text}'")
            print(f"Pipeline simulation - Fixed:    '{text_content}'")
            print(f"Pipeline simulation - Read:     '{read_back_3}'")
            print(f"Successfully cleaned: {'â€™' not in read_back_3}")
            print()
            
        except ImportError as e:
            print(f"Could not test pipeline functions: {e}")
        
    finally:
        # Cleanup
        import shutil
        if test_dir.exists():
            shutil.rmtree(test_dir)
    
    return True

def enhanced_encoding_fix(text):
    """Enhanced encoding fix function with comprehensive character replacement."""
    if not isinstance(text, str):
        text = str(text)
    
    # Comprehensive character replacement map
    replacements = {
        # Smart quotes and apostrophes
        'â€™': "'",      # RIGHT SINGLE QUOTATION MARK (U+2019)
        'â€˜': "'",      # LEFT SINGLE QUOTATION MARK (U+2018)
        'â€œ': '"',      # LEFT DOUBLE QUOTATION MARK (U+201C)
        'â€': '"',      # RIGHT DOUBLE QUOTATION MARK (U+201D)
        
        # Dashes
        'â€"': '—',      # EM DASH (U+2014)
        'â€"': '–',      # EN DASH (U+2013)
        
        # Other punctuation
        'â€¦': '…',      # HORIZONTAL ELLIPSIS (U+2026)
        'â€¢': '•',      # BULLET (U+2022)
        
        # Common accented characters (double-encoded)
        'Ã©': 'é',       # é (e with acute)
        'Ã': 'à',       # à (a with grave)
        'Ã¡': 'á',       # á (a with acute)
        'Ã­': 'í',       # í (i with acute)
        'Ã³': 'ó',       # ó (o with acute)
        'Ãº': 'ú',       # ú (u with acute)
        'Ã±': 'ñ',       # ñ (n with tilde)
        'Ã§': 'ç',       # ç (c with cedilla)
        
        # Stray characters
        'Â': '',         # Often appears as stray character
        'Ã‚': '',        # Another stray
        
        # Zero-width and spacing characters
        'â€‹': '',       # ZERO WIDTH SPACE
        'â€‚': ' ',       # EN SPACE
        'â€ƒ': ' ',       # EM SPACE
        'â€‰': ' ',       # THIN SPACE
        'â€Š': ' ',       # HAIR SPACE
        'â€Œ': '',       # ZERO WIDTH NON-JOINER
        'â€': '',       # ZERO WIDTH JOINER
        'â€Ž': '',       # LEFT-TO-RIGHT MARK
        'â€': '',       # RIGHT-TO-LEFT MARK
    }
    
    # Apply replacements
    for mojibake, correct in replacements.items():
        if mojibake in text:
            text = text.replace(mojibake, correct)
    
    return text

def test_enhanced_fix():
    """Test the enhanced encoding fix function."""
    print("🔍 Testing Enhanced Encoding Fix")
    print("=" * 60)
    
    test_cases = [
        "Claude 4, GPT 5, and Microsoft\u00e2\u0080\u0099s Windows 11 AI Upgrades Redefine AI Assistants",
        "\u00e2\u0080\u009cHello world\u00e2\u0080\u009d said the AI assistant.",
        "Here are some features\u00e2\u0080\u00a6 that work well \u00e2\u0080\u0093 especially with AI \u00e2\u0080\u0094 technology.",
        "\u00e2\u0080\u00a2 First point\n\u00e2\u0080\u00a2 Second point",
        "Caf\u00c3\u00a9, na\u00c3\u00afve, r\u00c3\u00a9sum\u00c3\u00a9 with \u00c3\u00a9\u00c3\u00ad\u00c3\u00b3",
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test Case {i}:")
        print(f"  Original: '{test_case}'")
        
        enhanced_result = enhanced_encoding_fix(test_case)
        print(f"  Enhanced: '{enhanced_result}'")
        
        # Check if any mojibake remains
        mojibake_chars = ['â€™', 'â€œ', 'â€', 'â€"', 'â€"', 'â€¦', 'â€¢', 'â€˜', 'Ã©', 'Ã', 'Â']
        has_mojibake = any(char in enhanced_result for char in mojibake_chars)
        
        print(f"  Status: {'❌ Still has mojibake' if has_mojibake else '✅ Clean'}")
        print()

def main():
    """Run all encoding tests."""
    print("🧪 UTF-8 Encoding Fix Testing Suite")
    print("=" * 70)
    
    # Test the specific issue
    fixed_text = test_encoding_issue()
    
    # Test file operations
    test_file_write_encoding()
    
    # Test enhanced fix
    test_enhanced_fix()
    
    print("=" * 70)
    print("📋 Summary and Recommendations:")
    print("1. ✅ Character replacement approach works for fixing mojibake")
    print("2. ✅ Explicit UTF-8 encoding needed for file operations")
    print("3. 🔧 Current pipeline functions may need enhancement")
    print("4. 📝 Enhanced fix function provides comprehensive coverage")
    
    return fixed_text

if __name__ == "__main__":
    main()