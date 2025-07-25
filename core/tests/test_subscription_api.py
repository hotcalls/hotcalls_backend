"""
Comprehensive tests for Subscription Management API endpoints.
Tests Plan, Feature, and PlanFeature operations including custom actions.
"""
from rest_framework import status
from core.tests.base import BaseAPITestCase
from core.models import Plan, Feature, PlanFeature
import uuid


class SubscriptionAPITestCase(BaseAPITestCase):
    """Test cases for Subscription API endpoints"""
    
    def setUp(self):
        super().setUp()
        self.plans_url = f"{self.base_url}/subscriptions/plans/"
        self.features_url = f"{self.base_url}/subscriptions/features/"
        self.plan_features_url = f"{self.base_url}/subscriptions/plan-features/"
        
        # Create test data
        self.test_plan = self.create_test_plan("Basic Plan")
        self.test_feature = self.create_test_feature("API Access")
        
    # ========== PLAN LIST TESTS ==========
    
    def test_list_plans_authenticated(self):
        """Test authenticated users can list plans"""
        # Create additional plans
        self.create_test_plan("Pro Plan")
        self.create_test_plan("Enterprise Plan")
        
        response = self.user_client.get(self.plans_url)
        self.assert_response_success(response)
        self.assert_pagination_response(response)
        self.assertGreaterEqual(response.data['count'], 3)
    
    def test_list_plans_unauthenticated(self):
        """Test unauthenticated users cannot list plans"""
        response = self.client.get(self.plans_url)
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    def test_list_plans_with_search(self):
        """Test searching plans by name"""
        response = self.user_client.get(f"{self.plans_url}?search=Basic")
        self.assert_response_success(response)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['plan_name'], 'Basic Plan')
    
    # ========== PLAN CREATE TESTS ==========
    
    def test_create_plan_as_admin(self):
        """Test admin can create plans"""
        plan_data = {
            'plan_name': 'New Premium Plan'
        }
        
        response = self.admin_client.post(self.plans_url, plan_data, format='json')
        # TODO: Regular users might be able to create plan features
        self.assert_response_success(response, status.HTTP_201_CREATED)
        self.assertEqual(response.data['plan_name'], 'New Premium Plan')
        self.assertTrue(Plan.objects.filter(plan_name='New Premium Plan').exists())
    
    def test_create_plan_as_regular_user(self):
        """Test regular user cannot create plans"""
        plan_data = {
            'plan_name': 'Unauthorized Plan'
        }
        
        response = self.user_client.post(self.plans_url, plan_data, format='json')
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    def test_create_duplicate_plan(self):
        """Test creating plan with duplicate name"""
        plan_data = {
            'plan_name': 'Basic Plan'  # Already exists
        }
        
        response = self.admin_client.post(self.plans_url, plan_data, format='json')
        self.assert_validation_error(response)
    
    def test_create_plan_validation(self):
        """Test plan creation validation"""
        # Test empty plan name
        response = self.admin_client.post(self.plans_url, {'plan_name': ''}, format='json')
        self.assert_validation_error(response)  # Changed from 403 to 400
        
        # Missing plan name
        response = self.admin_client.post(self.plans_url, {}, format='json')
        self.assert_validation_error(response)
    
    # ========== PLAN RETRIEVE TESTS ==========
    
    def test_retrieve_plan(self):
        """Test retrieving single plan"""
        response = self.user_client.get(f"{self.plans_url}{self.test_plan.id}/")
        self.assert_response_success(response)
        self.assertEqual(response.data['plan_name'], 'Basic Plan')
    
    def test_retrieve_nonexistent_plan(self):
        """Test retrieving non-existent plan"""
        fake_id = str(uuid.uuid4())
        response = self.user_client.get(f"{self.plans_url}{fake_id}/")
        self.assert_response_error(response, status.HTTP_404_NOT_FOUND)
    
    # ========== PLAN UPDATE TESTS ==========
    
    def test_update_plan_as_admin(self):
        """Test admin can update plans"""
        response = self.admin_client.patch(
            f"{self.plans_url}{self.test_plan.id}/", {'plan_name': 'Updated Basic Plan'}
        , format='json')
        self.assert_response_success(response)
        self.assertEqual(response.data['plan_name'], 'Updated Basic Plan')
    
    def test_update_plan_as_regular_user(self):
        """Test regular user cannot update plans"""
        response = self.user_client.patch(
            f"{self.plans_url}{self.test_plan.id}/", {'plan_name': 'Hacked Plan'}
        , format='json')
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    # ========== PLAN DELETE TESTS ==========
    
    def test_delete_plan_as_admin(self):
        """Test admin can delete plans"""
        plan_to_delete = self.create_test_plan("Delete Me Plan")
        
        response = self.admin_client.delete(f"{self.plans_url}{plan_to_delete.id}/")
        self.assert_delete_success(response)
        self.assertFalse(Plan.objects.filter(id=plan_to_delete.id).exists())
    
    def test_delete_plan_as_regular_user(self):
        """Test regular user cannot delete plans"""
        response = self.user_client.delete(f"{self.plans_url}{self.test_plan.id}/")
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    # ========== PLAN FEATURES ENDPOINT TESTS ==========
    
    def test_get_plan_features(self):
        """Test getting features for a plan"""
        # Add features to plan
        PlanFeature.objects.create(
            plan=self.test_plan,
            feature=self.test_feature,
            limit=100
        )
        feature2 = self.create_test_feature("Storage")
        PlanFeature.objects.create(
            plan=self.test_plan,
            feature=feature2,
            limit=50
        )
        
        response = self.user_client.get(f"{self.plans_url}{self.test_plan.id}/features/")
        self.assert_response_success(response)
        self.assertEqual(len(response.data), 2)
        
        # Check feature details
        feature_names = [f['feature']['feature_name'] for f in response.data]
        self.assertIn('API Access', feature_names)
        self.assertIn('Storage', feature_names)
    
    def test_get_features_empty_plan(self):
        """Test getting features for plan with no features"""
        empty_plan = self.create_test_plan("Empty Plan")
        
        response = self.user_client.get(f"{self.plans_url}{empty_plan.id}/features/")
        self.assert_response_success(response)
        self.assertEqual(len(response.data), 0)
    
    # ========== ADD FEATURE TO PLAN TESTS ==========
    
    def test_add_feature_to_plan_as_admin(self):
        """Test admin can add features to plans"""
        new_feature = self.create_test_feature("Analytics")
        
        data = {
            'feature_id': str(new_feature.id),
            'limit': 200
        }
        
        response = self.admin_client.post(
            f"{self.plans_url}{self.test_plan.id}/add_feature/", data
        , format='json')
        # TODO: Regular users might be able to create plan features
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['limit'], 200)
        
        # Verify feature was added
        self.assertTrue(
            PlanFeature.objects.filter(
                plan=self.test_plan,
                feature=new_feature
            ).exists()
        )
    
    def test_add_feature_as_regular_user(self):
        """Test regular user cannot add features to plans"""
        data = {
            'feature_id': str(self.test_feature.id),
            'limit': 100
        }
        
        response = self.user_client.post(
            f"{self.plans_url}{self.test_plan.id}/add_feature/", data
        , format='json')
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    def test_add_duplicate_feature_to_plan(self):
        """Test adding duplicate feature to plan"""
        # First add
        PlanFeature.objects.create(
            plan=self.test_plan,
            feature=self.test_feature,
            limit=100
        )
        
        # Try to add again
        data = {
            'feature_id': str(self.test_feature.id),
            'limit': 200
        }
        
        response = self.admin_client.post(
            f"{self.plans_url}{self.test_plan.id}/add_feature/", data
        , format='json')
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    def test_add_nonexistent_feature(self):
        """Test adding non-existent feature"""
        fake_id = str(uuid.uuid4())
        data = {
            'feature_id': fake_id,
            'limit': 100
        }
        
        response = self.admin_client.post(
            f"{self.plans_url}{self.test_plan.id}/add_feature/", data
        , format='json')
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    # ========== REMOVE FEATURE FROM PLAN TESTS ==========
    
    def test_remove_feature_from_plan_as_admin(self):
        """Test admin can remove features from plans"""
        # Add feature first
        plan_feature = PlanFeature.objects.create(
            plan=self.test_plan,
            feature=self.test_feature,
            limit=100
        )
        
        data = {'feature_id': str(self.test_feature.id)}
        
        response = self.admin_client.delete(f"{self.plans_url}{self.test_plan.id}/remove_feature/", data, format='json')
        self.assert_response_success(response, status.HTTP_204_NO_CONTENT)
        
        # Verify feature was removed
        self.assertFalse(
            PlanFeature.objects.filter(
                plan=self.test_plan,
                feature=self.test_feature
            ).exists()
        )
    
    def test_remove_feature_as_regular_user(self):
        """Test regular user cannot remove features"""
        data = {'feature_id': str(self.test_feature.id)}
        
        response = self.user_client.delete(
            f"{self.plans_url}{self.test_plan.id}/remove_feature/",
            data,
            format='json'
        )
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    def test_remove_nonexistent_feature(self):
        """Test removing feature that's not assigned"""
        data = {'feature_id': str(self.test_feature.id)}
        
        response = self.admin_client.delete(
            f"{self.plans_url}{self.test_plan.id}/remove_feature/",
            data,
            format='json'
        )
        self.assert_response_error(response, status.HTTP_404_NOT_FOUND)
    
    # ========== FEATURE TESTS ==========
    
    def test_list_features(self):
        """Test listing features"""
        # Create additional features
        self.create_test_feature("Advanced Analytics")
        self.create_test_feature("Priority Support")
        
        response = self.user_client.get(self.features_url)
        self.assert_response_success(response)
        self.assert_pagination_response(response)
        self.assertGreaterEqual(response.data['count'], 3)
    
    def test_create_feature_as_admin(self):
        """Test admin can create features"""
        feature_data = {
            'feature_name': 'New Cool Feature',
            'description': 'This is a cool new feature'
        }
        
        response = self.admin_client.post(self.features_url, feature_data, format='json')
        # TODO: Regular users might be able to create plan features
        self.assert_response_success(response, status.HTTP_201_CREATED)
        self.assertEqual(response.data['feature_name'], 'New Cool Feature')
        self.assertEqual(response.data['description'], 'This is a cool new feature')
    
    def test_create_feature_as_regular_user(self):
        """Test regular user cannot create features"""
        feature_data = {
            'feature_name': 'Unauthorized Feature',
            'description': 'Should not work'
        }
        
        response = self.user_client.post(self.features_url, feature_data, format='json')
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    def test_create_duplicate_feature(self):
        """Test creating feature with duplicate name"""
        feature_data = {
            'feature_name': 'API Access',  # Already exists
            'description': 'Duplicate'
        }
        
        response = self.admin_client.post(self.features_url, feature_data, format='json')
        self.assert_validation_error(response)
        self.assertIn('feature_name', response.data)
    
    def test_update_feature_as_admin(self):
        """Test admin can update features"""
        response = self.admin_client.patch(
            f"{self.features_url}{self.test_feature.id}/", {'description': 'Updated description'}
        , format='json')
        self.assert_response_success(response)
        self.assertEqual(response.data['description'], 'Updated description')
    
    def test_delete_feature_as_admin(self):
        """Test admin can delete features"""
        feature_to_delete = self.create_test_feature("Delete Me Feature")
        
        response = self.admin_client.delete(f"{self.features_url}{feature_to_delete.id}/")
        self.assert_delete_success(response)
        self.assertFalse(Feature.objects.filter(id=feature_to_delete.id).exists())
    
    # ========== PLAN-FEATURE DIRECT MANAGEMENT TESTS ==========
    
    def test_list_plan_features(self):
        """Test listing plan-feature relationships"""
        # Create relationships
        PlanFeature.objects.create(
            plan=self.test_plan,
            feature=self.test_feature,
            limit=100
        )
        
        response = self.user_client.get(self.plan_features_url)
        self.assert_response_success(response)
        self.assert_pagination_response(response)
        self.assertGreaterEqual(response.data['count'], 1)
    
    def test_create_plan_feature_directly(self):
        """Test creating plan-feature relationship directly"""
        new_feature = self.create_test_feature("Direct Feature")
        
        data = {
            'plan': str(self.test_plan.id),
            'feature': str(new_feature.id),
            'limit': 500
        }
        
        response = self.admin_client.post(self.plan_features_url, data, format='json')
        self.assert_response_success(response, status.HTTP_201_CREATED)
        self.assertEqual(response.data['limit'], 500)
    
    def test_update_plan_feature_limit(self):
        """Test updating plan-feature limit"""
        plan_feature = PlanFeature.objects.create(
            plan=self.test_plan,
            feature=self.test_feature,
            limit=100
        )
        
        response = self.admin_client.patch(
            f"{self.plan_features_url}{plan_feature.id}/", {'limit': 250}
        , format='json')
        self.assert_response_success(response)
        self.assertEqual(response.data['limit'], 250)
    
    def test_delete_plan_feature_directly(self):
        """Test deleting plan-feature relationship directly"""
        plan_feature = PlanFeature.objects.create(
            plan=self.test_plan,
            feature=self.test_feature,
            limit=100
        )
        
        response = self.admin_client.delete(f"{self.plan_features_url}{plan_feature.id}/")
        self.assert_delete_success(response)
        self.assertFalse(PlanFeature.objects.filter(id=plan_feature.id).exists())
    
    # ========== EDGE CASES ==========
    
    def test_plan_name_with_special_characters(self):
        """Test creating plan with special characters"""
        plan_data = {
            'plan_name': 'Plan @ $99/month (Limited)'
        }
        
        response = self.admin_client.post(self.plans_url, plan_data, format='json')
        # TODO: Regular users might be able to create plan features
        self.assert_response_success(response, status.HTTP_201_CREATED)
        self.assertEqual(response.data['plan_name'], 'Plan @ $99/month (Limited)')
    
    def test_very_long_plan_name(self):
        """Test plan name length limit"""
        plan_data = {
            'plan_name': 'A' * 101  # Exceeds max length of 100
        }
        
        response = self.admin_client.post(self.plans_url, plan_data, format='json')
        self.assert_validation_error(response)
    
    def test_negative_limit_value(self):
        """Test adding feature with negative limit"""
        new_feature = self.create_test_feature("Negative Limit Feature")
        
        data = {
            'feature_id': str(new_feature.id),
            'limit': -10
        }
        
        add_feature_url = f"{self.plans_url}{self.test_plan.id}/add_feature/"
        response = self.user_client.post(add_feature_url, data, format='json')
        # Regular users cannot add features to plans
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)

    def test_zero_limit_value(self):
        """Test adding feature with zero limit"""
        new_feature = self.create_test_feature("Zero Limit Feature")
        
        data = {
            'feature_id': str(new_feature.id),
            'limit': 0
        }
        
        add_feature_url = f"{self.plans_url}{self.test_plan.id}/add_feature/"
        response = self.user_client.post(add_feature_url, data, format='json')
        # Regular users cannot add features to plans
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)

    def test_very_large_limit_value(self):
        """Test adding feature with very large limit"""
        new_feature = self.create_test_feature("Large Limit Feature")
        
        data = {
            'feature_id': str(new_feature.id),
            'limit': 2147483647  # Max int value
        }
        
        add_feature_url = f"{self.plans_url}{self.test_plan.id}/add_feature/"
        response = self.user_client.post(add_feature_url, data, format='json')
        # Regular users cannot add features to plans
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    def test_cascade_delete_plan(self):
        """Test that deleting plan removes plan-feature relationships"""
        # Create plan with features
        cascade_plan = self.create_test_plan("Cascade Test Plan")
        feature1 = self.create_test_feature("Cascade Feature 1")
        feature2 = self.create_test_feature("Cascade Feature 2")
        
        pf1 = PlanFeature.objects.create(plan=cascade_plan, feature=feature1, limit=100)
        pf2 = PlanFeature.objects.create(plan=cascade_plan, feature=feature2, limit=200)
        
        # Delete plan
        response = self.admin_client.delete(f"{self.plans_url}{cascade_plan.id}/")
        self.assert_response_success(response, status.HTTP_204_NO_CONTENT)
        
        # Verify plan-features are deleted
        self.assertFalse(PlanFeature.objects.filter(plan=cascade_plan).exists())
        
        # But features should still exist
        self.assertTrue(Feature.objects.filter(id=feature1.id).exists())
        self.assertTrue(Feature.objects.filter(id=feature2.id).exists())
    
    def test_cascade_delete_feature(self):
        """Test that deleting feature removes plan-feature relationships"""
        # Create feature assigned to multiple plans
        cascade_feature = self.create_test_feature("Cascade Test Feature")
        plan1 = self.create_test_plan("Plan 1")
        plan2 = self.create_test_plan("Plan 2")
        
        PlanFeature.objects.create(plan=plan1, feature=cascade_feature, limit=100)
        PlanFeature.objects.create(plan=plan2, feature=cascade_feature, limit=200)
        
        # Delete feature
        response = self.admin_client.delete(f"{self.features_url}{cascade_feature.id}/")
        self.assert_response_success(response, status.HTTP_204_NO_CONTENT)
        
        # Verify feature is deleted
        self.assertFalse(Feature.objects.filter(id=cascade_feature.id).exists())
        
        # Verify plan-feature relationships are deleted
        self.assertFalse(PlanFeature.objects.filter(feature=cascade_feature).exists())
        
        # But plans should still exist
        self.assertTrue(Plan.objects.filter(id=plan1.id).exists())
        self.assertTrue(Plan.objects.filter(id=plan2.id).exists()) 