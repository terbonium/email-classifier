#!/usr/bin/env python3
"""
Unit test for sender-based heuristics in email classification
"""
from classifier import EmailClassifier

def test_sender_heuristics():
    """Test that civic/government emails are properly classified"""
    classifier = EmailClassifier()

    # Test cases: (from_addr, expected_behavior)
    test_cases = [
        ('district7@info.miamidade.gov', 'Should reduce shopping probability for .gov domain'),
        ('notifications@university.edu', 'Should reduce shopping probability for .edu domain'),
        ('alerts@citygovernment.org', 'Should reduce shopping probability for .org domain'),
        ('contact@countyoffice.com', 'Should reduce shopping probability for civic keyword "county"'),
        ('info@commissioner.us', 'Should reduce shopping probability for civic keyword "commissioner"'),
        ('sales@retailstore.com', 'Should NOT reduce shopping probability for commercial domain'),
        ('user@personal.net', 'Should NOT reduce shopping probability for personal domain'),
    ]

    print("Testing sender-based heuristics...\n")

    for from_addr, expected in test_cases:
        # Simulate probabilities where shopping is high
        # Categories: ['personal', 'shopping', 'spam']
        original_probs = [0.2, 0.7, 0.1]  # Shopping is highest

        adjusted_probs = classifier.apply_sender_heuristics(from_addr, original_probs)

        shopping_idx = 1  # shopping is at index 1
        personal_idx = 0  # personal is at index 0

        is_civic = any([
            from_addr.endswith('.gov'),
            from_addr.endswith('.edu'),
            from_addr.endswith('.org'),
            'county' in from_addr,
            'city' in from_addr,
            'government' in from_addr,
            'commissioner' in from_addr,
            'district' in from_addr,
            'state' in from_addr,
            'municipal' in from_addr
        ])

        if is_civic:
            # Should have reduced shopping probability
            if adjusted_probs[shopping_idx] < original_probs[shopping_idx]:
                print(f"✓ PASS: {from_addr}")
                print(f"  Original: personal={original_probs[personal_idx]:.2f}, shopping={original_probs[shopping_idx]:.2f}, spam={original_probs[2]:.2f}")
                print(f"  Adjusted: personal={adjusted_probs[personal_idx]:.2f}, shopping={adjusted_probs[shopping_idx]:.2f}, spam={adjusted_probs[2]:.2f}")
                print(f"  {expected}\n")
            else:
                print(f"✗ FAIL: {from_addr}")
                print(f"  Shopping probability should have been reduced but wasn't")
                print(f"  Original: shopping={original_probs[shopping_idx]:.2f}")
                print(f"  Adjusted: shopping={adjusted_probs[shopping_idx]:.2f}\n")
        else:
            # Should NOT have reduced shopping probability
            if adjusted_probs[shopping_idx] == original_probs[shopping_idx]:
                print(f"✓ PASS: {from_addr}")
                print(f"  {expected}")
                print(f"  Probabilities unchanged as expected\n")
            else:
                print(f"✗ FAIL: {from_addr}")
                print(f"  Shopping probability should NOT have been reduced but was")
                print(f"  Original: shopping={original_probs[shopping_idx]:.2f}")
                print(f"  Adjusted: shopping={adjusted_probs[shopping_idx]:.2f}\n")

    print("\nTest complete!")

if __name__ == '__main__':
    test_sender_heuristics()
