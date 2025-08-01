"""
Django management command to create the Basic plan with quota features and endpoint restrictions.
"""
from django.core.management.base import BaseCommand
from decimal import Decimal
from core.models import Plan, Feature, PlanFeature, EndpointFeature


class Command(BaseCommand):
    help = 'Create Basic plan with specified quota limits and endpoint restrictions'

    def handle(self, *args, **options):
        self.stdout.write('Creating Basic plan with quota features...')
        
        # Create or get the Basic plan
        basic_plan, created = Plan.objects.get_or_create(
            plan_name='Basic',
            defaults={
                'price_monthly': Decimal('29.99'),
                'description': 'Basic plan with essential features for small teams'
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS(f'✓ Created plan: {basic_plan.plan_name}'))
        else:
            self.stdout.write(f'Plan "{basic_plan.plan_name}" already exists, updating features...')
        
        # Create features for the Basic plan
        features_data = [
            {
                'name': 'CALL_MINUTES',
                'description': 'Monthly call minutes allowance',
                'unit': 'minute',
                'limit': 100
            },
            {
                'name': 'AGENTS',
                'description': 'Number of AI agents allowed',
                'unit': 'general_unit',
                'limit': 3
            },
            {
                'name': 'WORKSPACES',
                'description': 'Number of workspaces allowed',
                'unit': 'general_unit',
                'limit': 2
            },
            {
                'name': 'USERS',
                'description': 'Number of users allowed per workspace',
                'unit': 'general_unit',
                'limit': 5
            },
            {
                'name': 'BULK_OPERATIONS',
                'description': 'Bulk operations like bulk create leads',
                'unit': 'request',
                'limit': 0  # Restricted - 0 means not allowed
            }
        ]
        
        created_features = []
        for feature_data in features_data:
            feature, feature_created = Feature.objects.get_or_create(
                feature_name=feature_data['name'],
                defaults={
                    'description': feature_data['description'],
                    'unit': feature_data['unit']
                }
            )
            
            if feature_created:
                self.stdout.write(f'  ✓ Created feature: {feature.feature_name}')
            
            created_features.append((feature, feature_data['limit']))
        
        # Link features to the Basic plan with limits
        for feature, limit in created_features:
            plan_feature, pf_created = PlanFeature.objects.get_or_create(
                plan=basic_plan,
                feature=feature,
                defaults={'limit': Decimal(str(limit))}
            )
            
            if not pf_created:
                # Update existing limit
                plan_feature.limit = Decimal(str(limit))
                plan_feature.save()
                self.stdout.write(f'  ↻ Updated limit for {feature.feature_name}: {limit}')
            else:
                self.stdout.write(f'  ✓ Set {feature.feature_name} limit: {limit}')
        
        # Create endpoint restriction for bulk create leads
        bulk_feature = Feature.objects.get(feature_name='BULK_OPERATIONS')
        
        # Define the bulk create leads endpoint (adjust route name as needed)
        endpoint_mapping, endpoint_created = EndpointFeature.objects.get_or_create(
            route_name='lead_api:lead-bulk-create',  # Adjust this to match your actual route name
            http_method='POST',
            defaults={'feature': bulk_feature}
        )
        
        if endpoint_created:
            self.stdout.write(f'  ✓ Created endpoint restriction: {endpoint_mapping.route_name} -> {bulk_feature.feature_name}')
        else:
            self.stdout.write(f'  ↻ Endpoint restriction already exists: {endpoint_mapping.route_name}')
        
        # Summary
        self.stdout.write(self.style.SUCCESS('\n🎉 Basic Plan Created Successfully!'))
        self.stdout.write(self.style.SUCCESS('\n📋 Plan Summary:'))
        self.stdout.write(f'Plan Name: {basic_plan.plan_name}')
        self.stdout.write(f'Monthly Price: ${basic_plan.price_monthly}')
        self.stdout.write('\n📊 Features & Limits:')
        
        for plan_feature in PlanFeature.objects.filter(plan=basic_plan):
            limit_text = str(plan_feature.limit) if plan_feature.limit > 0 else "RESTRICTED"
            unit_text = f" {plan_feature.feature.unit}" if plan_feature.feature.unit != 'general_unit' else ""
            self.stdout.write(f'  • {plan_feature.feature.feature_name}: {limit_text}{unit_text}')
        
        self.stdout.write('\n🚫 Restricted Endpoints:')
        for endpoint in EndpointFeature.objects.filter(feature__planfeature__plan=basic_plan, feature__planfeature__limit=0):
            self.stdout.write(f'  • {endpoint.http_method} {endpoint.route_name}')
        
        self.stdout.write(self.style.SUCCESS('\n✅ Ready to enforce quotas for Basic plan users!'))