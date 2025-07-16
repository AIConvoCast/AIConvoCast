def fix_text_encoding(text):
    """Fix common encoding issues in text, particularly mojibake characters."""
    if not isinstance(text, str):
        return str(text)
    
    # Check for mojibake characters
    if 'â€™' in text or 'â€œ' in text or 'â€' in text:
        print(f"⚠️  ENCODING ISSUE DETECTED in text!")
        print(f"Original text sample: {text[:200]}...")
        
        try:
            # Common mojibake fix: encode as latin1, decode as utf-8
            fixed_text = text.encode('latin1').decode('utf-8')
            print(f"Fixed text sample: {fixed_text[:200]}...")
            return fixed_text
        except Exception as e:
            print(f"Failed to fix encoding with latin1 method: {e}")
            
            try:
                # Alternative fix: replace common mojibake patterns
                replacements = {
                    'â€™': "'",
                    'â€œ': '"',
                    'â€': '"',
                    'â€"': '—',
                    'â€¦': '…',
                    'â€¢': '•',
                    'â€"': '–',
                    'â€˜': "'",
                    'â€™': "'",
                    'â€œ': '"',
                    'â€': '"'
                }
                fixed_text = text
                for mojibake, correct in replacements.items():
                    fixed_text = fixed_text.replace(mojibake, correct)
                print(f"Fixed text with replacements sample: {fixed_text[:200]}...")
                return fixed_text
            except Exception as e2:
                print(f"Failed to fix encoding with replacements: {e2}")
                return text
    
    return text

# Test with the actual problematic text from the user
test_text = """Today we will be talking about Meta's massive infrastructure spending, the European Union's new voluntary code of practice, and cutting-edge advances in AI driven drug discovery.

Meta kicked off this week with a bold plan to invest between sixty and sixty-five billion dollars in capital expenditures next year, up from about thirty-eight to forty billion dollars this year. Mark Zuckerberg described the data center theyâ€™re building as having over two gigawatts of capacity, â€œso large it would cover a significant part of Manhattan.â€ Meta plans to spread these facilities across multiple sites worldwide, all designed for energy efficiency at this unprecedented scale. On top of that, theyâ€™re aiming to deploy more than one point three million graphics processing units by the end of next year and bring roughly one gigawatt of computing power online. Coming on the heels of Microsoftâ€™s eighty billion dollar data center commitment and Amazonâ€™s seventy-five plus billion, this move keeps Meta in step with the biggest infrastructure players."""

print("Testing encoding fix function...")
print("=" * 50)
print("Original text:")
print(test_text[:300])
print("\n" + "=" * 50)

fixed_text = fix_text_encoding(test_text)
print("\nFixed text:")
print(fixed_text[:300])
print("\n" + "=" * 50)

# Check if the fix worked
if 'â€™' in fixed_text or 'â€œ' in fixed_text or 'â€' in fixed_text:
    print("❌ ENCODING ISSUE STILL PRESENT!")
    print(f"Found mojibake characters: â€™ in text: {'â€™' in fixed_text}")
    print(f"Found mojibake characters: â€œ in text: {'â€œ' in fixed_text}")
    print(f"Found mojibake characters: â€ in text: {'â€' in fixed_text}")
else:
    print("✅ ENCODING FIX SUCCESSFUL!") 