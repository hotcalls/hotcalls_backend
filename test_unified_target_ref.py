#!/usr/bin/env python3
"""
Test script to verify unified target_ref approach for script template rendering.

This script tests both lead and test_user scenarios to ensure consistent
template variable mapping across all call types.
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


def test_unified_target_ref_approach():
    """Test the unified target_ref approach for both lead and test_user scenarios."""
    
    print("🧪 Testing Unified Target Ref Script Template Rendering")
    print("=" * 60)
    
    # Test template with all possible variables
    test_template = """Hello {{ name }} {{ surname }}!

Your contact information:
- Email: {{ email }}
- Phone: {{ phone }}

{% if budget %}Budget: ${{ budget }}{% endif %}
{% if company %}Company: {{ company }}{% endif %}
{% if interest %}Interest: {{ interest }}{% endif %}

Thank you for your time!"""

    print(f"📝 Test Template:")
    print(test_template)
    print("\n" + "=" * 60)
    
    # Test cases for different target_ref scenarios
    test_cases = [
        {
            "name": "Lead Target Ref",
            "target_ref": "lead:123e4567-e89b-12d3-a456-426614174000", 
            "description": "Real call with lead and custom variables"
        },
        {
            "name": "Test User Target Ref", 
            "target_ref": "test_user:987fcdeb-51a2-43d6-ba89-0123456789ab",
            "description": "Test call with user data only"
        },
        {
            "name": "Invalid Target Ref",
            "target_ref": "invalid:12345",
            "description": "Invalid target_ref should fallback gracefully"
        },
        {
            "name": "Empty Target Ref",
            "target_ref": "",
            "description": "Empty target_ref should return original template"
        }
    ]
    
    print("🔬 Running Test Cases:")
    print("-" * 60)
    
    success_count = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. {test_case['name']}")
        print(f"   Target Ref: '{test_case['target_ref']}'")
        print(f"   Description: {test_case['description']}")
        
        try:
            # Test the unified approach
            rendered = script_template_service.render_script_for_target_ref(
                test_template, 
                test_case['target_ref']
            )
            
            print(f"   ✅ Rendering successful")
            print(f"   📏 Length: {len(test_template)} → {len(rendered)} chars")
            
            # Show first few lines of rendered output
            preview = rendered.split('\n')[:3]
            print(f"   📄 Preview: {preview[0][:50]}{'...' if len(preview[0]) > 50 else ''}")
            
            success_count += 1
            
        except Exception as e:
            print(f"   ❌ Error: {type(e).__name__}: {e}")
    
    print("\n" + "=" * 60)
    print(f"🎯 Test Results: {success_count}/{len(test_cases)} tests passed")
    
    # Test context creation directly
    print("\n🔍 Testing Context Creation:")
    print("-" * 60)
    
    context_test_cases = [
        "lead:123e4567-e89b-12d3-a456-426614174000",
        "test_user:987fcdeb-51a2-43d6-ba89-0123456789ab" 
    ]
    
    for target_ref in context_test_cases:
        print(f"\n📋 Context for '{target_ref}':")
        try:
            context = script_template_service.create_context_from_target_ref(target_ref)
            print(f"   Keys: {list(context.keys())}")
            print(f"   Name: '{context.get('name', 'N/A')}'")
            print(f"   Surname: '{context.get('surname', 'N/A')}'") 
            print(f"   Email: '{context.get('email', 'N/A')}'")
            print(f"   Phone: '{context.get('phone', 'N/A')}'")
            
            # Show custom variables count for leads
            custom_vars = {k: v for k, v in context.items() 
                          if k not in ['name', 'surname', 'email', 'phone']}
            if custom_vars:
                print(f"   Custom Variables: {list(custom_vars.keys())}")
            
        except Exception as e:
            print(f"   ❌ Error: {type(e).__name__}: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Unified Target Ref Testing Complete!")
    

def test_render_methods_comparison():
    """Compare the different rendering methods for consistency."""
    
    print("\n🔄 Testing Method Consistency:")
    print("-" * 60)
    
    # Simple template for comparison
    simple_template = "Hello {{ name }} {{ surname }}! Email: {{ email }}"
    
    # Test different methods with the same data
    test_target_ref = "lead:123e4567-e89b-12d3-a456-426614174000"
    
    try:
        # Method 1: Unified target_ref approach (new)
        result1 = script_template_service.render_script_for_target_ref(
            simple_template, test_target_ref
        )
        
        # Method 2: Create context manually then render
        context = script_template_service.create_context_from_target_ref(test_target_ref)
        result2 = script_template_service.render_script_template(
            simple_template, context
        )
        
        print(f"📊 Method Comparison Results:")
        print(f"   Target Ref Method: '{result1[:50]}{'...' if len(result1) > 50 else ''}'")
        print(f"   Context Method:    '{result2[:50]}{'...' if len(result2) > 50 else ''}'")
        print(f"   Results Match: {'✅ Yes' if result1 == result2 else '❌ No'}")
        
        if result1 != result2:
            print(f"   Length Diff: {len(result1)} vs {len(result2)}")
        
    except Exception as e:
        print(f"   ❌ Comparison Error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    test_unified_target_ref_approach()
    test_render_methods_comparison()
    print("\n🏁 All tests completed!")