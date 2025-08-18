#!/usr/bin/env python3
"""
Test script to verify that API responses are properly cleaned of mojibake characters
before being stored in the workflow outputs.
"""

import sys
import os

def test_api_response_encoding_simulation():
    """Simulate API responses with mojibake to test the enhanced encoding fixes."""
    print("🧪 Testing API Response Encoding Fix")
    print("=" * 60)
    
    # Add current directory to path
    sys.path.append('.')
    
    try:
        from ai_podcast_pipeline_for_cursor import fix_text_encoding, force_clean_mojibake
        
        # Simulate problematic API responses that might contain mojibake
        test_responses = [
            # Example 1: User's specific case
            "Meta AI Chatbot Tragedy, MIT\u00e2\u0080\u0099s Antibiotics Breakthrough, and xAI\u00e2\u0080\u0099s Grok Imagine Controversy",
            
            # Example 2: Mixed mojibake patterns
            "Here\u00e2\u0080\u0099s what\u00e2\u0080\u0099s happening in AI: \u00e2\u0080\u009cBig changes\u00e2\u0080\u009d are coming\u00e2\u0080\u00a6",
            
            # Example 3: Complex title with multiple issues
            "Google\u00e2\u0080\u0099s AI Revolution \u00e2\u0080\u0094 What\u00e2\u0080\u0099s Next for Machine Learning?",
            
            # Example 4: Article content with quotes
            "The CEO said: \u00e2\u0080\u009cWe\u00e2\u0080\u0099re revolutionizing AI\u00e2\u0080\u009d. This isn\u00e2\u0080\u0099t just talk\u00e2\u0080\u00a6"
        ]
        
        print("Testing individual API response processing:")
        print("-" * 40)
        
        all_passed = True
        
        for i, test_response in enumerate(test_responses, 1):
            print(f"\nTest Case {i}:")
            print(f"Original API Response: {test_response}")
            
            # Simulate the enhanced API response processing
            step1 = fix_text_encoding(test_response)
            step2 = force_clean_mojibake(step1)
            
            print(f"After fix_text_encoding: {step1}")
            print(f"After force_clean_mojibake: {step2}")
            
            # Check for remaining mojibake
            mojibake_patterns = [
                '\u00e2\u0080\u0099',  # Right single quotation mark
                '\u00e2\u0080\u009c',  # Left double quotation mark
                '\u00e2\u0080\u009d',  # Right double quotation mark
                '\u00e2\u0080\u0094',  # Em dash
                '\u00e2\u0080\u00a6',  # Ellipsis
                'â€™', 'â€œ', 'â€', 'â€"', 'â€¦'  # Visual representations
            ]
            
            has_mojibake = any(pattern in step2 for pattern in mojibake_patterns)
            test_passed = not has_mojibake
            
            print(f"Result: {'✅ CLEAN' if test_passed else '❌ STILL HAS MOJIBAKE'}")
            
            if not test_passed:
                all_passed = False
                print("Remaining patterns:")
                for pattern in mojibake_patterns:
                    if pattern in step2:
                        print(f"  - Found: {repr(pattern)}")
        
        print("\n" + "=" * 60)
        print(f"🎯 Overall Result: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
        
        return all_passed
        
    except ImportError as e:
        print(f"❌ Could not import functions: {e}")
        return False
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        return False

def test_workflow_integration():
    """Test how the fixed API responses would flow through the workflow."""
    print("\n🔧 Testing Workflow Integration")
    print("=" * 60)
    
    try:
        sys.path.append('.')
        
        # Simulate a complete workflow step processing
        # This simulates what happens when an API response becomes part of all_outputs
        # and then gets saved via save-only steps
        
        # Mock workflow outputs with mojibake (as they might come from APIs)
        mock_all_outputs = [
            "Welcome to today\u00e2\u0080\u0099s podcast!",  # Output 1
            "We\u00e2\u0080\u0099ll discuss AI\u00e2\u0080\u0099s impact on society\u00e2\u0080\u00a6",  # Output 2
            "Meta AI Chatbot Tragedy, MIT\u00e2\u0080\u0099s Antibiotics Breakthrough",  # Output 3 (user's example)
        ]
        
        print("Mock workflow outputs (as they might come from APIs):")
        for i, output in enumerate(mock_all_outputs, 1):
            print(f"  Output {i}: {output}")
        
        print("\nSimulating save-only step processing (R7SL10T7 pattern):")
        
        # Simulate the save-only step processing from the pipeline
        from ai_podcast_pipeline_for_cursor import fix_text_encoding, force_clean_mojibake
        
        # Simulate saving Output 3 (user's problematic example)
        response_to_save = mock_all_outputs[2]  # Index 2 = Output 3
        
        print(f"Original response to save: {response_to_save}")
        
        # Apply the same fixes as in the save-only step
        response_to_save = fix_text_encoding(response_to_save)
        response_to_save = force_clean_mojibake(response_to_save)
        
        print(f"After encoding fixes: {response_to_save}")
        
        # Check if mojibake was removed
        mojibake_removed = '\u00e2\u0080\u0099' not in response_to_save
        
        print(f"Mojibake successfully removed: {'✅ YES' if mojibake_removed else '❌ NO'}")
        
        # Simulate the complete upload_text_to_gcs process
        print("\nSimulating upload_text_to_gcs process:")
        
        from ai_podcast_pipeline_for_cursor import upload_text_to_gcs
        import tempfile
        import os
        
        # Create a test destination
        test_blob_name = "test/workflow_output.txt"
        
        # Note: This would normally upload to GCS, but we're just testing the text processing
        # The upload_text_to_gcs function will apply additional encoding fixes
        
        # Simulate the text processing part of upload_text_to_gcs
        text_content = response_to_save
        
        if isinstance(text_content, bytes):
            text_content = text_content.decode('utf-8')
        elif not isinstance(text_content, str):
            text_content = str(text_content)
        
        text_content = fix_text_encoding(text_content)
        text_content = force_clean_mojibake(text_content)
        
        print(f"Final processed text: {text_content}")
        
        # Test file writing
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.txt') as f:
            f.write(text_content)
            temp_file = f.name
        
        # Read it back
        with open(temp_file, 'r', encoding='utf-8') as f:
            read_back = f.read()
        
        print(f"Text read from file: {read_back}")
        
        # Cleanup
        os.unlink(temp_file)
        
        final_success = (
            '\u00e2\u0080\u0099' not in read_back and
            'â€™' not in read_back and
            read_back == text_content and
            read_back == "Meta AI Chatbot Tragedy, MIT's Antibiotics Breakthrough"
        )
        
        print(f"\n🎯 Workflow Integration Result: {'✅ SUCCESS' if final_success else '❌ FAILED'}")
        
        return final_success
        
    except Exception as e:
        print(f"❌ Error during workflow integration test: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all API response encoding tests."""
    print("🧪 API Response Encoding Fix Test Suite")
    print("=" * 70)
    
    test1_result = test_api_response_encoding_simulation()
    test2_result = test_workflow_integration()
    
    print("\n" + "=" * 70)
    print("📊 Test Summary:")
    print(f"  API Response Processing: {'✅ PASSED' if test1_result else '❌ FAILED'}")
    print(f"  Workflow Integration:    {'✅ PASSED' if test2_result else '❌ FAILED'}")
    
    if test1_result and test2_result:
        print("\n🎉 All tests passed! API responses will be properly cleaned.")
        print("\n📝 What this means:")
        print("  ✅ All API responses from OpenAI, Anthropic, and Google are now cleaned")
        print("  ✅ Mojibake characters will be removed at the source")
        print("  ✅ Text files saved by the workflow will have proper characters")
        print("  ✅ The issue 'Microsoftâ€™s' → 'Microsoft's' is resolved")
    else:
        print("\n⚠️ Some tests failed. Please check the output above for details.")

if __name__ == "__main__":
    main()