#!/usr/bin/env python3
"""
Test the enhanced encoding fix with the user's specific example.
"""

import sys
import os

def test_user_example():
    """Test the specific example provided by the user."""
    # Add the current directory to path to import the pipeline
    sys.path.append('.')
    
    try:
        from ai_podcast_pipeline_for_cursor import force_clean_mojibake, fix_text_encoding
        
        # The user's problematic text
        problematic_text = "Claude 4, GPT 5, and Microsoft\u00e2\u0080\u0099s Windows 11 AI Upgrades Redefine AI Assistants"
        
        print("🔧 Testing Enhanced Encoding Fix")
        print("=" * 60)
        print(f"Original text: {problematic_text}")
        print(f"Contains mojibake: {'â' in problematic_text}")
        print()
        
        # Test fix_text_encoding first
        fixed_1 = fix_text_encoding(problematic_text)
        print(f"After fix_text_encoding: {fixed_1}")
        print(f"Still has mojibake: {'â' in fixed_1}")
        print()
        
        # Test force_clean_mojibake
        fixed_2 = force_clean_mojibake(fixed_1)
        print(f"After force_clean_mojibake: {fixed_2}")
        print(f"Still has mojibake: {'â' in fixed_2}")
        print()
        
        # Test the complete pipeline process (both functions)
        complete_fix = force_clean_mojibake(fix_text_encoding(problematic_text))
        print(f"Complete pipeline fix: {complete_fix}")
        print(f"Still has mojibake: {'â' in complete_fix}")
        print()
        
        # Check specific patterns
        mojibake_patterns = [
            '\u00e2\u0080\u0099',  # The specific pattern from user's example
            'â€™',                 # Visual representation
            'â€œ',                 # Left double quote
            'â€',                 # Right double quote
        ]
        
        print("Pattern detection:")
        for pattern in mojibake_patterns:
            in_original = pattern in problematic_text
            in_fixed = pattern in complete_fix
            print(f"  {repr(pattern)}: Original={in_original}, Fixed={in_fixed}")
        
        # Final verdict
        success = not any(pattern in complete_fix for pattern in mojibake_patterns)
        print()
        print(f"🎯 Final Result: {'✅ SUCCESS' if success else '❌ FAILED'}")
        
        if success:
            print("✅ The enhanced encoding fix successfully handles the user's example!")
        else:
            print("❌ Some mojibake patterns still remain. Need further enhancement.")
            
        return success
        
    except ImportError as e:
        print(f"❌ Could not import pipeline functions: {e}")
        return False
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        return False

def test_save_simulation():
    """Simulate the complete save process."""
    print("\n🔧 Testing Complete Save Process Simulation")
    print("=" * 60)
    
    try:
        sys.path.append('.')
        from ai_podcast_pipeline_for_cursor import upload_text_to_gcs
        
        # Simulate problematic text that might come from an AI model
        test_text = "Here's the title: Claude 4, GPT 5, and Microsoft\u00e2\u0080\u0099s Windows 11 AI Upgrades Redefine AI Assistants"
        
        print(f"Input text: {test_text}")
        print(f"Contains mojibake: {'â' in test_text}")
        print()
        
        # This would call upload_text_to_gcs in the real pipeline
        # For testing, we'll just simulate the text processing part
        from ai_podcast_pipeline_for_cursor import fix_text_encoding, force_clean_mojibake
        
        # Apply the same processing as in upload_text_to_gcs
        processed_text = test_text
        if isinstance(processed_text, bytes):
            processed_text = processed_text.decode('utf-8')
        elif not isinstance(processed_text, str):
            processed_text = str(processed_text)
        
        processed_text = fix_text_encoding(processed_text)
        processed_text = force_clean_mojibake(processed_text)
        
        print(f"Processed text: {processed_text}")
        print(f"Still has mojibake: {'â' in processed_text}")
        
        # Test file writing with UTF-8
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.txt') as f:
            f.write(processed_text)
            temp_file = f.name
        
        # Read it back
        with open(temp_file, 'r', encoding='utf-8') as f:
            read_back = f.read()
        
        print(f"Read back from file: {read_back}")
        print(f"File read matches processed: {read_back == processed_text}")
        
        # Cleanup
        os.unlink(temp_file)
        
        success = 'â' not in processed_text and read_back == processed_text
        print(f"\n🎯 Save Simulation Result: {'✅ SUCCESS' if success else '❌ FAILED'}")
        
        return success
        
    except Exception as e:
        print(f"❌ Error during save simulation: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Enhanced UTF-8 Encoding Fix Test")
    print("=" * 70)
    
    test1_result = test_user_example()
    test2_result = test_save_simulation()
    
    print("\n" + "=" * 70)
    print("📊 Test Summary:")
    print(f"  User Example Test: {'✅ PASSED' if test1_result else '❌ FAILED'}")
    print(f"  Save Process Test: {'✅ PASSED' if test2_result else '❌ FAILED'}")
    
    if test1_result and test2_result:
        print("\n🎉 All tests passed! UTF-8 encoding issues should be resolved.")
    else:
        print("\n⚠️ Some tests failed. Check the output above for details.")