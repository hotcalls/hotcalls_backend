from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from datetime import timezone as dt_timezone
from .models import User, Voice, Plan, Feature, PlanFeature, Workspace, Agent, PhoneNumber, Lead, Blacklist, CallLog, Calendar, CalendarConfiguration
from .models import (
    GoogleCalendarConnection, GoogleCalendar, WorkspaceSubscription, 
    WorkspaceUsage, FeatureUsage, EndpointFeature, MetaIntegration, 
    WorkspaceInvitation, SIPTrunk, MetaLeadForm, LeadFunnel, WebhookLeadSource,
    LeadProcessingStats, LiveKitAgent
)
from django.utils import timezone


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    """Custom admin for email-based User model"""
    
    # Display settings
    list_display = ('email', 'first_name', 'last_name', 'phone', 'status', 'is_email_verified', 'is_staff', 'date_joined')
    list_filter = ('status', 'is_staff', 'is_superuser', 'is_active', 'is_email_verified', 'date_joined', 'social_provider')
    search_fields = ('email', 'first_name', 'last_name', 'phone')
    ordering = ('-date_joined',)
    
    # Form fieldsets for editing existing users
    fieldsets = (
        (None, {
            'fields': ('email', 'password')
        }),
        ('Personal info', {
            'fields': ('first_name', 'last_name', 'phone')
        }),
        ('Email Verification', {
            'fields': ('is_email_verified', 'email_verification_sent_at'),
            'classes': ('collapse',)
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important dates', {
            'fields': ('last_login', 'date_joined')
        }),
        ('Custom Fields', {
            'fields': ('status', 'stripe_customer_id', 'social_id', 'social_provider')
        }),
    )
    
    # Form fieldsets for adding new users
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'phone', 'password1', 'password2'),
        }),
        ('Permissions', {
            'fields': ('is_staff', 'is_superuser'),
        }),
        ('Custom Fields', {
            'fields': ('status', 'stripe_customer_id', 'social_id', 'social_provider'),
        }),
    )
    
    # Read-only fields (encrypted token fields are hidden via editable=False)
    readonly_fields = ('date_joined', 'last_login', 'email_verification_sent_at')
    
    # Filter horizontal for many-to-many fields
    filter_horizontal = ('groups', 'user_permissions')


@admin.register(Voice)
class VoiceAdmin(admin.ModelAdmin):
    """Admin for Voice model"""
    list_display = ('voice_external_id', 'provider', 'created_at', 'updated_at')
    list_filter = ('provider', 'created_at')
    search_fields = ('voice_external_id', 'provider')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ('feature_name', 'unit', 'description', 'created_at')
    list_filter = ('unit', 'created_at')
    search_fields = ('feature_name', 'description')
    ordering = ('feature_name',)


@admin.register(PlanFeature)
class PlanFeatureAdmin(admin.ModelAdmin):
    list_display = ('plan', 'feature', 'limit', 'created_at')
    list_filter = ('plan', 'feature', 'created_at')
    search_fields = ('plan__plan_name', 'feature__feature_name')
    ordering = ('plan', 'feature')


@admin.register(EndpointFeature)
class EndpointFeatureAdmin(admin.ModelAdmin):
    list_display = ('route_name', 'http_method', 'feature', 'created_at')
    list_filter = ('http_method', 'feature', 'feature__unit', 'created_at')
    search_fields = ('route_name', 'feature__feature_name')
    ordering = ('route_name', 'http_method')
    
    fieldsets = (
        ('Endpoint Info', {
            'fields': ('route_name', 'http_method')
        }),
        ('Feature Mapping', {
            'fields': ('feature',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('created_at', 'updated_at')


# Inline classes need to be defined first
class PlanFeatureInline(admin.TabularInline):
    model = PlanFeature
    extra = 1


class GoogleCalendarInline(admin.TabularInline):
    model = GoogleCalendar
    extra = 0
    fields = ('external_id', 'primary', 'time_zone')
    readonly_fields = ('external_id', 'primary', 'time_zone', 'created_at', 'updated_at')


class CalendarInline(admin.TabularInline):
    model = Calendar
    extra = 0
    fields = ('name', 'provider', 'active')
    readonly_fields = ('created_at', 'updated_at')


class CalendarConfigurationInline(admin.TabularInline):
    model = CalendarConfiguration
    extra = 0
    fields = ('duration', 'prep_time', 'days_buffer', 'from_time', 'to_time')


class WorkspaceSubscriptionInline(admin.TabularInline):
    model = WorkspaceSubscription
    extra = 0
    fields = ('plan', 'started_at', 'ends_at', 'is_active')
    readonly_fields = ('created_at', 'updated_at')


class FeatureUsageInline(admin.TabularInline):
    model = FeatureUsage
    extra = 0
    fields = ('feature', 'used_amount')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('plan_name', 'get_features_count', 'created_at', 'updated_at')
    search_fields = ('plan_name',)
    ordering = ('plan_name',)
    inlines = [PlanFeatureInline]
    
    def get_features_count(self, obj):
        return obj.features.count()
    get_features_count.short_description = 'Features Count'


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ('workspace_name', 'get_current_plan', 'get_calendars_count', 'get_google_connections_count', 'created_at', 'updated_at')
    search_fields = ('workspace_name',)
    filter_horizontal = ('users',)
    ordering = ('workspace_name',)
    inlines = [WorkspaceSubscriptionInline, CalendarInline]
    
    def get_current_plan(self, obj):
        current_plan = obj.current_plan
        return current_plan.plan_name if current_plan else 'No Plan'
    get_current_plan.short_description = 'Current Plan'
    
    def get_calendars_count(self, obj):
        return obj.calendars.count()
    get_calendars_count.short_description = 'Calendars'
    
    def get_google_connections_count(self, obj):
        return obj.google_calendar_connections.filter(active=True).count()
    get_google_connections_count.short_description = 'Google Connections'


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ('agent_id', 'workspace', 'name', 'status', 'voice', 'language', 'get_phone_number', 'calendar_configuration', 'created_at')
    list_filter = ('status', 'voice', 'language', 'phone_number', 'calendar_configuration', 'created_at')
    search_fields = ('name', 'workspace__workspace_name', 'voice__voice_external_id', 'phone_number__phonenumber')
    ordering = ('-created_at',)
    
    def get_phone_number(self, obj):
        return obj.phone_number.phonenumber if obj.phone_number else 'No phone assigned'
    get_phone_number.short_description = 'Phone Number'
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "calendar_configuration":
            # Only show calendar configurations from the agent's workspace
            if hasattr(request, '_obj_'):
                kwargs["queryset"] = CalendarConfiguration.objects.filter(
                    calendar__workspace=request._obj_.workspace
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def get_form(self, request, obj=None, **kwargs):
        # Store the object in request for use in formfield_for_foreignkey
        request._obj_ = obj
        return super().get_form(request, obj, **kwargs)


@admin.register(PhoneNumber)
class PhoneNumberAdmin(admin.ModelAdmin):
    list_display = ('phonenumber', 'get_agents', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('phonenumber',)
    ordering = ('-created_at',)
    
    def get_agents(self, obj):
        return ", ".join([f"{agent.workspace.workspace_name}" for agent in obj.agents.all()])
    get_agents.short_description = 'Agents'


@admin.register(SIPTrunk)
class SIPTrunkAdmin(admin.ModelAdmin):
    list_display = (
        'provider_name', 'sip_host', 'sip_port', 'jambonz_carrier_id', 'livekit_trunk_id', 'is_active', 'created_at'
    )
    list_filter = ('provider_name', 'is_active', 'created_at')
    search_fields = ('provider_name', 'sip_host', 'jambonz_carrier_id', 'livekit_trunk_id')
    ordering = ('-created_at',)


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('name', 'surname', 'email', 'phone', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'surname', 'email', 'phone')
    ordering = ('-created_at',)


@admin.register(Blacklist)
class BlacklistAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'reason', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'reason')
    ordering = ('-created_at',)


@admin.register(CallLog)
class CallLogAdmin(admin.ModelAdmin):
    list_display = ('lead', 'agent', 'from_number', 'to_number', 'direction', 'status', 'duration', 'timestamp')
    list_filter = ('direction', 'status', 'timestamp', 'disconnection_reason')
    search_fields = ('lead__name', 'lead__surname', 'agent__name', 'from_number', 'to_number')
    ordering = ('-timestamp',)
    readonly_fields = ('timestamp', 'updated_at')


@admin.register(GoogleCalendarConnection)
class GoogleCalendarConnectionAdmin(admin.ModelAdmin):
    list_display = ('workspace', 'account_email', 'active', 'get_calendars_count', 'last_sync', 'created_at')
    list_filter = ('active', 'workspace', 'last_sync', 'created_at')
    search_fields = ('workspace__workspace_name', 'account_email')
    ordering = ('-created_at',)
    readonly_fields = ('access_token', 'refresh_token', 'token_expires_at', 'scopes', 'sync_errors', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Connection Info', {
            'fields': ('workspace', 'user', 'account_email', 'active')
        }),
        ('OAuth Tokens (Read Only)', {
            'fields': ('access_token', 'refresh_token', 'token_expires_at', 'scopes'),
            'classes': ('collapse',)
        }),
        ('Sync Status', {
            'fields': ('last_sync', 'sync_errors'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_calendars_count(self, obj):
        return obj.calendars.count()
    get_calendars_count.short_description = 'Calendars'


@admin.register(GoogleCalendar)
class GoogleCalendarAdmin(admin.ModelAdmin):
    list_display = ('get_calendar_name', 'external_id', 'primary', 'time_zone', 'created_at')
    list_filter = ('primary', 'time_zone', 'created_at')
    search_fields = ('external_id', 'calendar__name', 'calendar__workspace__workspace_name')
    ordering = ('-created_at',)
    readonly_fields = ('external_id', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Calendar Info', {
            'fields': ('calendar', 'external_id', 'primary', 'time_zone')
        }),
        ('OAuth Tokens', {
            'fields': ('refresh_token', 'access_token', 'token_expires_at', 'scopes'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_calendar_name(self, obj):
        return obj.calendar.name
    get_calendar_name.short_description = 'Calendar Name'
    get_calendar_name.admin_order_field = 'calendar__name'


@admin.register(Calendar)
class CalendarAdmin(admin.ModelAdmin):
    list_display = ('name', 'workspace', 'provider', 'active', 'get_configs_count', 'get_connection_status', 'created_at')
    list_filter = ('provider', 'active', 'workspace', 'created_at')
    search_fields = ('name', 'workspace__workspace_name')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [CalendarConfigurationInline, GoogleCalendarInline]
    
    def get_configs_count(self, obj):
        return obj.configurations.count()
    get_configs_count.short_description = 'Configurations'
    
    def get_connection_status(self, obj):
        if obj.provider == 'google' and hasattr(obj, 'google_calendar'):
            # Check if the Google calendar has valid tokens
            google_cal = obj.google_calendar
            if google_cal.token_expires_at:
                # Make timezone-aware comparison
                token_expiry = google_cal.token_expires_at
                if token_expiry.tzinfo is None:
                    # Convert naive datetime to timezone-aware
                    token_expiry = token_expiry.replace(tzinfo=dt_timezone.utc)
                
                if token_expiry > timezone.now():
                    return '✅ Connected'
                else:
                    return '⚠️ Token Expired'
            else:
                return '⚠️ No Token'
        return '❓ Unknown'
    get_connection_status.short_description = 'Status'


@admin.register(CalendarConfiguration)
class CalendarConfigurationAdmin(admin.ModelAdmin):
    list_display = ('get_workspace', 'get_calendar_name', 'get_provider', 'duration', 'prep_time', 'days_buffer', 'from_time', 'to_time', 'get_conflict_calendars_count')
    list_filter = ('calendar__provider', 'calendar__workspace', 'duration', 'days_buffer', 'created_at')
    search_fields = ('calendar__workspace__workspace_name', 'calendar__name')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Calendar Info', {
            'fields': ('calendar',)
        }),
        ('Scheduling Settings', {
            'fields': ('duration', 'prep_time', 'days_buffer')
        }),
        ('Availability Window', {
            'fields': ('from_time', 'to_time', 'workdays')
        }),
        ('Conflict Checking', {
            'fields': ('conflict_check_calendars',),
            'description': 'List of calendar IDs to check for scheduling conflicts'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_workspace(self, obj):
        return obj.calendar.workspace.workspace_name
    get_workspace.short_description = 'Workspace'
    
    def get_calendar_name(self, obj):
        return obj.calendar.name
    get_calendar_name.short_description = 'Calendar'
    
    def get_provider(self, obj):
        return obj.calendar.provider.title()
    get_provider.short_description = 'Provider'
    
    def get_conflict_calendars_count(self, obj):
        """Show number of calendars configured for conflict checking"""
        if obj.conflict_check_calendars:
            return f"{len(obj.conflict_check_calendars)} calendars"
        return "None"
    get_conflict_calendars_count.short_description = 'Conflict Check'


@admin.register(WorkspaceSubscription)
class WorkspaceSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('workspace', 'plan', 'started_at', 'ends_at', 'is_active', 'created_at')
    list_filter = ('is_active', 'plan', 'started_at', 'ends_at', 'created_at')
    search_fields = ('workspace__workspace_name', 'plan__plan_name')
    ordering = ('-started_at',)
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Subscription Info', {
            'fields': ('workspace', 'plan', 'is_active')
        }),
        ('Period', {
            'fields': ('started_at', 'ends_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(WorkspaceUsage)
class WorkspaceUsageAdmin(admin.ModelAdmin):
    list_display = ('workspace', 'subscription', 'period_start', 'period_end', 'get_features_count')
    list_filter = ('workspace', 'subscription__plan', 'period_start', 'period_end')
    search_fields = ('workspace__workspace_name', 'subscription__plan__plan_name')
    ordering = ('-period_start',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [FeatureUsageInline]
    
    def get_features_count(self, obj):
        return obj.feature_usages.count()
    get_features_count.short_description = 'Features Used'


@admin.register(FeatureUsage)
class FeatureUsageAdmin(admin.ModelAdmin):
    list_display = ('get_workspace', 'feature', 'used_amount', 'get_period', 'updated_at')
    list_filter = ('feature', 'feature__unit', 'usage_record__period_start')
    search_fields = ('usage_record__workspace__workspace_name', 'feature__feature_name')
    ordering = ('-updated_at',)
    readonly_fields = ('created_at', 'updated_at')
    
    def get_workspace(self, obj):
        return obj.usage_record.workspace.workspace_name
    get_workspace.short_description = 'Workspace'
    
    def get_period(self, obj):
        return f"{obj.usage_record.period_start.date()} → {obj.usage_record.period_end.date()}"
    get_period.short_description = 'Period'


@admin.register(MetaIntegration)
class MetaIntegrationAdmin(admin.ModelAdmin):
    list_display = ('workspace', 'page_id', 'status', 'access_token_expires_at', 'created_at')
    list_filter = ('status', 'access_token_expires_at', 'created_at')
    search_fields = ('workspace__workspace_name', 'page_id')
    ordering = ('-created_at',)
    readonly_fields = ('access_token', 'verification_token', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Meta Integration Info', {
            'fields': ('workspace', 'page_id', 'status')
        }),
        ('OAuth Tokens (Read Only - Encrypted)', {
            'fields': ('access_token_expires_at', 'scopes'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(WorkspaceInvitation)
class WorkspaceInvitationAdmin(admin.ModelAdmin):
    """Admin for WorkspaceInvitation model"""
    list_display = ('email', 'workspace', 'invited_by', 'status', 'created_at', 'expires_at', 'is_valid_display')
    list_filter = ('status', 'workspace', 'created_at', 'expires_at')
    search_fields = ('email', 'workspace__workspace_name', 'invited_by__email')
    ordering = ('-created_at',)
    readonly_fields = ('token', 'created_at', 'accepted_at')
    
    fieldsets = (
        ('Invitation Info', {
            'fields': ('workspace', 'email', 'invited_by', 'status')
        }),
        ('Security', {
            'fields': ('token',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'expires_at', 'accepted_at'),
            'classes': ('collapse',)
        }),
    )
    
    def is_valid_display(self, obj):
        """Display if invitation is valid with colored indicator"""
        if obj.is_valid():
            return '✅ Valid'
        else:
            return '❌ Invalid/Expired'
    is_valid_display.short_description = 'Valid'
    
    def get_readonly_fields(self, request, obj=None):
        """Make certain fields readonly based on object state"""
        readonly = list(self.readonly_fields)
        if obj and obj.status != 'pending':
            # Don't allow editing workspace/email after acceptance
            readonly.extend(['workspace', 'email', 'invited_by'])
        return readonly


@admin.register(MetaLeadForm)
class MetaLeadFormAdmin(admin.ModelAdmin):
    list_display = ('meta_integration', 'meta_form_id', 'name', 'is_active', 'created_at')
    list_filter = ('meta_integration__workspace', 'created_at')
    search_fields = ('meta_form_id', 'name', 'meta_integration__workspace__workspace_name')
    ordering = ('-created_at',)


@admin.register(LeadFunnel)
class LeadFunnelAdmin(admin.ModelAdmin):
    list_display = ('name', 'workspace', 'meta_lead_form', 'is_active', 'created_at')
    list_filter = ('workspace', 'is_active', 'created_at')
    search_fields = ('name', 'workspace__workspace_name', 'meta_lead_form__meta_form_id')
    ordering = ('-created_at',)


@admin.register(WebhookLeadSource)
class WebhookLeadSourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'workspace', 'lead_funnel', 'created_at', 'updated_at')
    list_filter = ('workspace', 'created_at')
    search_fields = ('name', 'workspace__workspace_name')
    ordering = ('-created_at',)


@admin.register(LeadProcessingStats)
class LeadProcessingStatsAdmin(admin.ModelAdmin):
    list_display = ('workspace', 'date', 'total_received', 'processed_with_agent', 'processing_rate')
    list_filter = ('workspace', 'date')
    search_fields = ('workspace__workspace_name',)
    ordering = ('-date',)


@admin.register(LiveKitAgent)
class LiveKitAgentAdmin(admin.ModelAdmin):
    list_display = ('name', 'concurrency_per_agent', 'expires_at', 'created_at')
    list_filter = ('expires_at', 'created_at')
    search_fields = ('name', 'token')
    ordering = ('-created_at',)
