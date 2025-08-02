from django.core.management.base import BaseCommand, CommandError
from core.models import Plan, Feature, PlanFeature
from decimal import Decimal


class Command(BaseCommand):
    help = 'Setup subscription plans and features for HotCalls'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation of plans and features (deletes existing)',
        )

    def handle(self, *args, **options):
        """Main command handler"""
        force = options['force']
        
        self.stdout.write(
            self.style.SUCCESS('🚀 Setting up HotCalls subscription plans...')
        )
        
        if force:
            self.stdout.write('⚠️ Force mode: Deleting existing plans and features...')
            Plan.objects.all().delete()
            Feature.objects.all().delete()
            self.stdout.write(self.style.WARNING('✅ Existing data deleted'))
        
        # Create features
        features = self._create_features()
        
        # Create plans with features
        self._create_plans(features)
        
        # Assign Enterprise plan to existing superusers
        self._assign_enterprise_to_superusers()
        
        self.stdout.write(
            self.style.SUCCESS('🎉 Successfully setup all plans and features!')
        )

    def _create_features(self):
        """Create all required features"""
        self.stdout.write('📋 Creating features...')
        
        # NOTE: Added `unit` to align with new quota/feature system
        feature_definitions = [
            {
                'name': 'call_minutes',
                'description': 'Included call minutes per month',
                'unit': 'minute',
            },
            {
                'name': 'overage_rate_cents',
                'description': 'Cost per minute after included minutes are used (in cents)',
                'unit': 'general_unit',
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
            {
                'name': 'whitelabel_solution',
                'description': 'White-label branding and customization',
                'unit': 'access',
            },
            {
                'name': 'crm_integrations',
                'description': 'CRM system integrations',
                'unit': 'access',
            },
            {
                'name': 'priority_support',
                'description': 'Priority customer support',
                'unit': 'access',
            },
            {
                'name': 'custom_voice_cloning',
                'description': 'Custom voice cloning capabilities',
                'unit': 'access',
            },
            {
                'name': 'advanced_analytics',
                'description': 'Advanced analytics and reporting',
                'unit': 'access',
            },
        ]
        
        features = {}
        for feature_def in feature_definitions:
            feature, created = Feature.objects.get_or_create(
                feature_name=feature_def['name'],
                defaults={
                    'description': feature_def['description'],
                    'unit': feature_def.get('unit', 'general_unit'),
                },
            )

            # Ensure existing record has correct description/unit
            updated = False
            if not created:
                if feature.description != feature_def['description']:
                    feature.description = feature_def['description']
                    updated = True
                desired_unit = feature_def.get('unit', 'general_unit')
                if feature.unit != desired_unit:
                    feature.unit = desired_unit
                    updated = True
                if updated:
                    feature.save(update_fields=['description', 'unit'])
            
            features[feature_def['name']] = feature
            
            status = '✅ Created' if created else ('🔄 Updated' if updated else '✔️ Unchanged')
            self.stdout.write(f'  {status}: {feature.feature_name}')
        
        return features

    def _create_plans(self, features):
        """Create all subscription plans"""
        self.stdout.write('💳 Creating subscription plans...')
        
        # START PLAN
        start_plan = self._create_plan(
            name='Start',
            price_monthly=Decimal('199.00'),
            description='Ideal für Einzelpersonen und kleine Teams',
            stripe_product_id='prod_start_hotcalls',
            stripe_price_id_monthly='price_start_monthly_199'
        )
        
        # Add features to Start plan
        self._add_feature_to_plan(start_plan, features['call_minutes'], 250)
        self._add_feature_to_plan(start_plan, features['overage_rate_cents'], 49)  # 0,49€ = 49 Cent
        self._add_feature_to_plan(start_plan, features['max_users'], 1)  # 1 User
        self._add_feature_to_plan(start_plan, features['max_agents'], 1)  # 1 Agent pro Workspace
        
        # PRO PLAN
        pro_plan = self._create_plan(
            name='Pro',
            price_monthly=Decimal('549.00'),
            description='Am beliebtesten - Ideal für Unternehmen mit höherem Volumen',
            stripe_product_id='prod_pro_hotcalls',
            stripe_price_id_monthly='price_pro_monthly_549'
        )
        
        # Add features to Pro plan
        self._add_feature_to_plan(pro_plan, features['call_minutes'], 1000)
        self._add_feature_to_plan(pro_plan, features['overage_rate_cents'], 29)  # 0,29€ = 29 Cent
        self._add_feature_to_plan(pro_plan, features['max_users'], 3)  # 3 User
        self._add_feature_to_plan(pro_plan, features['max_agents'], 3)  # 3 Agents pro Workspace
        
        # ENTERPRISE PLAN
        enterprise_plan = self._create_plan(
            name='Enterprise',
            price_monthly=None,  # Individuell
            description='Individuelle Lösungen für große Unternehmen und Agenturen - Preis auf Anfrage',
            stripe_product_id='prod_enterprise_hotcalls',
            stripe_price_id_monthly=None  # Enterprise hat keinen festen Preis
        )
        
        # Add features to Enterprise plan
        self._add_feature_to_plan(enterprise_plan, features['call_minutes'], 999999)  # Unlimited
        self._add_feature_to_plan(enterprise_plan, features['overage_rate_cents'], 0)  # No overage
        self._add_feature_to_plan(enterprise_plan, features['max_users'], 999999)  # Unlimited users
        self._add_feature_to_plan(enterprise_plan, features['max_agents'], 999999)  # Unlimited agents
        self._add_feature_to_plan(enterprise_plan, features['whitelabel_solution'], 1)
        self._add_feature_to_plan(enterprise_plan, features['crm_integrations'], 1)
        self._add_feature_to_plan(enterprise_plan, features['priority_support'], 2)  # Premium support
        self._add_feature_to_plan(enterprise_plan, features['advanced_analytics'], 1)
        self._add_feature_to_plan(enterprise_plan, features['custom_voice_cloning'], 1)

    def _create_plan(self, name, price_monthly, description, stripe_product_id=None, stripe_price_id_monthly=None):
        """Create a single plan with Stripe IDs"""
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
            # Update existing plan with new Stripe IDs
            plan.price_monthly = price_monthly
            plan.stripe_product_id = stripe_product_id
            plan.stripe_price_id_monthly = stripe_price_id_monthly
            plan.save()
        
        status = '✅ Created' if created else '🔄 Updated'
        price_display = f'{price_monthly}€' if price_monthly else 'Individuell'
        self.stdout.write(f'  {status}: {name} Plan ({price_display}/Monat)')
        
        # Show Stripe IDs if available
        if stripe_product_id:
            self.stdout.write(f'      🔗 Stripe Product: {stripe_product_id}')
        if stripe_price_id_monthly:
            self.stdout.write(f'      💳 Stripe Price: {stripe_price_id_monthly}')
        
        return plan

    def _add_feature_to_plan(self, plan, feature, limit):
        """Add a feature to a plan with specified limit"""
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

    def _assign_enterprise_to_superusers(self):
        """Assign Enterprise plan to existing superusers without active subscriptions"""
        from django.contrib.auth import get_user_model
        from django.utils import timezone
        from core.models import Workspace, WorkspaceSubscription
        
        User = get_user_model()
        self.stdout.write('👑 Checking superusers for Enterprise plan assignment...')
        
        # Get Enterprise plan
        try:
            enterprise_plan = Plan.objects.get(plan_name='Enterprise')
        except Plan.DoesNotExist:
            self.stdout.write(self.style.ERROR('❌ Enterprise plan not found! Create plans first.'))
            return
        
        superusers = User.objects.filter(is_superuser=True)
        assigned_count = 0
        
        for superuser in superusers:
            # Check if superuser has any workspace with active subscription
            has_active_subscription = False
            for workspace in superuser.mapping_user_workspaces.all():
                if WorkspaceSubscription.objects.filter(workspace=workspace, is_active=True).exists():
                    has_active_subscription = True
                    break
            
            if not has_active_subscription:
                # Create workspace if superuser doesn't have one
                if not superuser.mapping_user_workspaces.exists():
                    workspace = Workspace.objects.create(
                        workspace_name=f"{superuser.first_name} {superuser.last_name} Admin Workspace".strip() or f"Admin Workspace ({superuser.email})"
                    )
                    workspace.users.add(superuser)
                    self.stdout.write(f'  📁 Created workspace for {superuser.email}')
                else:
                    workspace = superuser.mapping_user_workspaces.first()
                
                # Create Enterprise subscription
                WorkspaceSubscription.objects.create(
                    workspace=workspace,
                    plan=enterprise_plan,
                    started_at=timezone.now(),
                    is_active=True
                )
                
                assigned_count += 1
                self.stdout.write(f'  ✅ Assigned Enterprise plan to superuser: {superuser.email}')
        
        if assigned_count == 0:
            self.stdout.write('  ✔️ All superusers already have active subscriptions')
        else:
            self.stdout.write(self.style.SUCCESS(f'🎉 Assigned Enterprise plan to {assigned_count} superuser(s)')) 