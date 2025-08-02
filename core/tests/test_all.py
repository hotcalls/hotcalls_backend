"""
Test suite runner for all API tests.
Run this to execute all test cases at once.
"""
import unittest
from django.test.runner import DiscoverRunner

# Import all test cases
from .test_user_api import UserAPITestCase
from .test_workspace_api import WorkspaceAPITestCase
from .test_agent_api import AgentAPITestCase
from .test_lead_api import LeadAPITestCase
from .test_call_api import CallAPITestCase
from .test_calendar_api import CalendarAPITestCase


def suite():
    """Create test suite with all API tests"""
    test_suite = unittest.TestSuite()
    
    # Add all test classes
    test_classes = [
        UserAPITestCase,
        WorkspaceAPITestCase,
        AgentAPITestCase,
        LeadAPITestCase,
        CallAPITestCase,
        CalendarAPITestCase,
    ]
    
    loader = unittest.TestLoader()
    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    return test_suite


if __name__ == '__main__':
    # Run all tests
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite()) 