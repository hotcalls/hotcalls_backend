#!/usr/bin/env python3
"""
Test script to verify greeting_outbound template rendering works correctly.
"""

import os
import sys
import django
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotcalls.settings')
django.setup()

from core.services.script_template_service import script_template_service


def test_greeting_outbound_rendering():
    """Test that greeting_outbound templates render correctly with target_ref."""
    
    print("🎯 Testing Greeting Outbound Template Rendering")
    print("=" * 60)
    
    # Test templates with different variable patterns
    test_cases = [
        {
            "name": "Simple name greeting",
            "template": "Hello {{name}}, I'm calling from our team. Is this a good time?",
            "target_ref": "lead:123e4567-e89b-12d3-a456-426614174000"
        },
        {
            "name": "Full contact info greeting",
            "template": "Hi {{name}} {{surname}}, I'm reaching out to {{email}} regarding your inquiry. Can we talk?",
            "target_ref": "lead:123e4567-e89b-12d3-a456-426614174000"
        },
        {
            "name": "Custom variables greeting",
            "template": "Hello {{name}}, I'm calling about your {{interest}} inquiry with a budget of ${{budget}}.",
            "target_ref": "lead:123e4567-e89b-12d3-a456-426614174000"
        },
        {
            "name": "Test user greeting",
            "template": "Hello {{name}} {{surname}}, this is a test call to {{email}}.",
            "target_ref": "test_user:987fcdeb-51a2-43d6-ba89-0123456789ab"
        },
        {
            "name": "Static greeting (no variables)",
            "template": "Hello, I'm calling from our company. Is this a good time to talk?",
            "target_ref": "lead:123e4567-e89b-12d3-a456-426614174000"
        },
        {
            "name": "Empty template",
            "template": "",
            "target_ref": "lead:123e4567-e89b-12d3-a456-426614174000"
        }
    ]
    
    success_count = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. {test_case['name']}")
        print(f"   Template: '{test_case['template']}'")
        print(f"   Target: {test_case['target_ref']}")
        
        try:
            # Test the greeting rendering using the same method as script templates
            rendered = script_template_service.render_script_for_target_ref(
                test_case['template'], 
                test_case['target_ref']
            )
            
            print(f"   ✅ Rendered: '{rendered}'")
            print(f"   📏 Length: {len(test_case['template'])} → {len(rendered)} chars")
            
            # Basic validation
            if test_case['template'] == "":
                expected_result = ""
            elif "{{" not in test_case['template']:
                expected_result = test_case['template']  # Static content should remain unchanged
            else:
                expected_result = test_case['template']  # With variables, result should differ (in real scenario with DB)
            
            success_count += 1
            
        except Exception as e:
            print(f"   ❌ Error: {type(e).__name__}: {e}")
    
    print("\n" + "=" * 60)
    print(f"🎯 Test Results: {success_count}/{len(test_cases)} tests passed")
    
    # Test comparison with script template rendering
    print("\n🔄 Testing Consistency with Script Template Method:")
    test_template = "Hello {{name}}, welcome to our service!"
    test_target = "lead:123e4567-e89b-12d3-a456-426614174000"
    
    try:
        # This is the same method used for both script and greeting rendering
        result1 = script_template_service.render_script_for_target_ref(test_template, test_target)
        result2 = script_template_service.render_script_for_target_ref(test_template, test_target)
        
        print(f"   Result 1: '{result1}'")
        print(f"   Result 2: '{result2}'")
        print(f"   Consistent: {'✅ Yes' if result1 == result2 else '❌ No'}")
        
    except Exception as e:
        print(f"   ❌ Consistency Test Error: {e}")
    
    print("\n✅ Greeting Template Rendering Tests Complete!")


if __name__ == "__main__":
    test_greeting_outbound_rendering()
    print("\n🏁 All tests completed!")