from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Feature, Plan, PlanFeature, EndpointFeature
from decimal import Decimal

class Command(BaseCommand):

    @transaction.atomic
    def handle(self, *args, **options):
        features = self._ensure_features()
        self._create_plans(features)
        self._create_endpoint_mappings(features)
        return

    def _ensure_features(self):
        feature_definitions = [
            {
                'name': 'call_minutes',
                'description': 'Included call minutes per month',
                'unit': 'minute',
            },
            {
                'name': 'max_users',
                'description': 'Maximum number of users allowed in workspace',
                'unit': 'general_unit',
            },
            {
                'name': 'max_agents',
                'description': 'Maximum number of agents allowed per workspace',
                'unit': 'general_unit',
            },
        ]

        features = {}
        for feature_def in feature_definitions:
            feature, created = Feature.objects.get_or_create(
                feature_name=feature_def['name'],
                defaults={
                    'description': feature_def['description'],
                    'unit': feature_def['unit'],
                },
            )

            updated = False
            if not created:
                if feature.description != feature_def['description']:
                    feature.description = feature_def['description']
                    updated = True
                if feature.unit != feature_def['unit']:
                    feature.unit = feature_def['unit']
                    updated = True
                if updated:
                    feature.save(update_fields=['description', 'unit'])

            features[feature_def['name']] = feature

        return features

    def _create_plans(self, features):
        # START PLAN
        start_plan = self._create_plan(
            name='Start',
            price_monthly=Decimal('199.00'),
            stripe_product_id='prod_SlrPR8OxP3GpFW',
            stripe_price_id_monthly='price_1RqJh1Rreb0r83Oz2N9nVrl9'
        )

        # Add features to Start plan
        self._add_feature_to_plan(start_plan, features['call_minutes'], 250)
        self._add_feature_to_plan(start_plan, features['max_users'], 3)
        self._add_feature_to_plan(start_plan, features['max_agents'], 1)

        # PRO PLAN
        pro_plan = self._create_plan(
            name='Pro',
            price_monthly=Decimal('549.00'),
            stripe_product_id='prod_SlrQWBeZ7ecw6d',
            stripe_price_id_monthly='price_1RqJheRreb0r83OzM0jmhwzX'
        )

        # Add features to Pro plan
        self._add_feature_to_plan(pro_plan, features['call_minutes'], 1000)
        self._add_feature_to_plan(pro_plan, features['max_users'], 5)
        self._add_feature_to_plan(pro_plan, features['max_agents'], 3)

        # ENTERPRISE PLAN
        enterprise_plan = self._create_plan(
            name='Enterprise',
            price_monthly=None,
            stripe_product_id=None,  # No Stripe product - custom pricing
            stripe_price_id_monthly=None  # Enterprise hat keinen festen Preis
        )

        # Add features to Enterprise plan
        self._add_feature_to_plan(enterprise_plan, features['call_minutes'], 999999)  # Unlimited
        self._add_feature_to_plan(enterprise_plan, features['max_users'], 999999)  # Unlimited users
        self._add_feature_to_plan(enterprise_plan, features['max_agents'], 999999)  # Unlimited agents

    def _create_plan(self, name, price_monthly, stripe_product_id=None, stripe_price_id_monthly=None):
        plan, created = Plan.objects.get_or_create(
            plan_name=name,
            defaults={
                'price_monthly': price_monthly,
                'stripe_product_id': stripe_product_id,
                'stripe_price_id_monthly': stripe_price_id_monthly,
                'is_active': True
            }
        )

        if not created:
            plan.price_monthly = price_monthly
            plan.stripe_product_id = stripe_product_id
            plan.stripe_price_id_monthly = stripe_price_id_monthly
            plan.save()

        return plan

    def _add_feature_to_plan(self, plan, feature, limit):
        plan_feature, created = PlanFeature.objects.get_or_create(
            plan=plan,
            feature=feature,
            defaults={'limit': limit}
        )

        if not created and plan_feature.limit != limit:
            plan_feature.limit = limit
            plan_feature.save()

        limit_display = limit if limit != 999999 else 'Unlimited'
        status = '✅ Added' if created else '🔄 Updated'
        self.stdout.write(f'    {status}: {feature.feature_name} (limit: {limit_display})')

        return plan_feature

    def _create_endpoint_mappings(self, features):
        endpoint_mappings = [
            # =========================
            # VIRTUAL ROUTES (Internal Operations)
            # =========================
            {
                'route_name': 'internal:outbound_call',
                'http_method': 'POST',
                'feature': features['call_minutes'],
                'description': 'Outbound call quota check (amount=0, status check only)'
            },
            {
                'route_name': 'internal:call_duration_used',
                'http_method': 'POST',
                'feature': features['call_minutes'],
                'description': 'Recording actual call duration usage (from call log creation)'
            },

            # =========================
            # REAL API ROUTES (HTTP Endpoints)
            # =========================

            # Agent Management (consumes max_agents feature)
            {
                'route_name': 'agent_api:agent-list',
                'http_method': 'POST',
                'feature': features['max_agents'],
                'description': 'Creating new agents'
            },

            # User Management (consumes max_users feature)
            {
                'route_name': 'user_api:user-list',
                'http_method': 'POST',
                'feature': features['max_users'],
                'description': 'Adding users to workspace'
            },
            {
                'route_name': 'workspace_api:workspace-add-users',
                'http_method': 'POST',
                'feature': features['max_users'],
                'description': 'Adding users to workspace'
            },
        ]

        for mapping in endpoint_mappings:
            endpoint, created = EndpointFeature.objects.get_or_create(
                route_name=mapping['route_name'],
                http_method=mapping['http_method'],
                defaults={
                    'feature': mapping['feature']
                }
            )

            if not created and endpoint.feature != mapping['feature']:
                endpoint.feature = mapping['feature']
                endpoint.save()
