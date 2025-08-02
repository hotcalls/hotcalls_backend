from django.core.management.base import BaseCommand
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
        
        # Create endpoint mappings for quota enforcement
        self._create_endpoint_mappings(features)
        
        # Assign Enterprise plan to existing superusers
        self._assign_enterprise_to_superusers()
        
        self.stdout.write(
            self.style.SUCCESS('🎉 Successfully setup all plans and features!')
        )

    def _create_features(self):
        """Create all required features"""
        self.stdout.write('📋 Creating features...')
        
        # ONLY MEASURABLE/ENFORCEABLE FEATURES
        # Cosmetic features are now stored in Plan.cosmetic_features JSON field
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
            stripe_price_id_monthly='price_start_monthly_199',
            cosmetic_features={
                'whitelabel_solution': False,
                'crm_integrations': False,
                'priority_support': 'standard',
                'custom_voice_cloning': False,
                'advanced_analytics': False,
            }
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
            stripe_price_id_monthly='price_pro_monthly_549',
            cosmetic_features={
                'whitelabel_solution': False,
                'crm_integrations': True,
                'priority_support': 'premium',
                'custom_voice_cloning': False,
                'advanced_analytics': True,
            }
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
            stripe_price_id_monthly=None,  # Enterprise hat keinen festen Preis
            cosmetic_features={
                'whitelabel_solution': True,
                'crm_integrations': True,
                'priority_support': 'enterprise',
                'custom_voice_cloning': True,
                'advanced_analytics': True,
            }
        )
        
        # Add features to Enterprise plan
        self._add_feature_to_plan(enterprise_plan, features['call_minutes'], 999999)  # Unlimited
        self._add_feature_to_plan(enterprise_plan, features['overage_rate_cents'], 0)  # No overage
        self._add_feature_to_plan(enterprise_plan, features['max_users'], 999999)  # Unlimited users
        self._add_feature_to_plan(enterprise_plan, features['max_agents'], 999999)  # Unlimited agents

    def _create_plan(self, name, price_monthly, description, stripe_product_id=None, stripe_price_id_monthly=None, cosmetic_features=None):
        """Create a single plan with Stripe IDs and cosmetic features"""
        if cosmetic_features is None:
            cosmetic_features = {}
            
        plan, created = Plan.objects.get_or_create(
            plan_name=name,
            defaults={
                'price_monthly': price_monthly,
                'stripe_product_id': stripe_product_id,
                'stripe_price_id_monthly': stripe_price_id_monthly,
                'cosmetic_features': cosmetic_features,
                'is_active': True
            }
        )
        
        if not created:
            # Update existing plan with new data
            plan.price_monthly = price_monthly
            plan.stripe_product_id = stripe_product_id
            plan.stripe_price_id_monthly = stripe_price_id_monthly
            plan.cosmetic_features = cosmetic_features
            plan.save()
        
        status = '✅ Created' if created else '🔄 Updated'
        price_display = f'{price_monthly}€' if price_monthly else 'Individuell'
        self.stdout.write(f'  {status}: {name} Plan ({price_display}/Monat)')
        
        # Show Stripe IDs if available
        if stripe_product_id:
            self.stdout.write(f'      🔗 Stripe Product: {stripe_product_id}')
        if stripe_price_id_monthly:
            self.stdout.write(f'      💳 Stripe Price: {stripe_price_id_monthly}')
        
        # Show cosmetic features
        if cosmetic_features:
            enabled_features = [k for k, v in cosmetic_features.items() if v and v != 'standard']
            if enabled_features:
                self.stdout.write(f'      ✨ Cosmetic Features: {", ".join(enabled_features)}')
        
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

    def _create_endpoint_mappings(self, features):
        """Create EndpointFeature mappings for quota enforcement"""
        from core.models import EndpointFeature
        
        self.stdout.write('🔗 Creating endpoint mappings for quota enforcement...')
        
        # Define which API routes should be mapped to which features
        # Only map REAL implemented features to avoid quota blocking non-existent endpoints
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
            
            # NOTE: Overdraft protection is handled in trigger_call task - calls allowed
            # if not already in overdraft. Actual minutes recorded here when call log created.
            #
            # Premium features (crm_integrations, custom_voice_cloning, etc.) are not 
            # yet implemented in the API, so no endpoint mappings are created for them.
        ]
        
        created_count = 0
        updated_count = 0
        
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
                updated_count += 1
            elif created:
                created_count += 1
            
            status = '✅ Created' if created else ('🔄 Updated' if not created and endpoint.feature != mapping['feature'] else '✔️ Unchanged')
            self.stdout.write(f'  {status}: {mapping["route_name"]} ({mapping["http_method"]}) → {mapping["feature"].feature_name}')
        
        if created_count == 0 and updated_count == 0:
            self.stdout.write('  ✔️ All endpoint mappings already exist')
        else:
            self.stdout.write(
                self.style.SUCCESS(f'🎯 Created {created_count} and updated {updated_count} endpoint mappings')
            )

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