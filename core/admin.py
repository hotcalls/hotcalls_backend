from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Voice, Plan, Feature, PlanFeature, Workspace, Agent, PhoneNumber, Lead, Blacklist, CallLog, Calendar, CalendarConfiguration


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
            'fields': ('is_email_verified', 'email_verification_token', 'email_verification_sent_at'),
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
    
    # Read-only fields
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
    list_display = ('feature_name', 'description', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('feature_name', 'description')
    ordering = ('feature_name',)


@admin.register(PlanFeature)
class PlanFeatureAdmin(admin.ModelAdmin):
    list_display = ('plan', 'feature', 'limit', 'created_at')
    list_filter = ('plan', 'feature', 'created_at')
    search_fields = ('plan__plan_name', 'feature__feature_name')
    ordering = ('plan', 'feature')


# Inline classes need to be defined first
class PlanFeatureInline(admin.TabularInline):
    model = PlanFeature
    extra = 1


class CalendarInline(admin.TabularInline):
    model = Calendar
    extra = 0
    fields = ('calendar_type', 'account_id')
    readonly_fields = ('created_at', 'updated_at')


class CalendarConfigurationInline(admin.TabularInline):
    model = CalendarConfiguration
    extra = 0
    fields = ('sub_calendar_id', 'duration', 'prep_time', 'days_buffer', 'from_time', 'to_time')


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
    list_display = ('workspace_name', 'get_calendars_count', 'created_at', 'updated_at')
    search_fields = ('workspace_name',)
    filter_horizontal = ('users',)
    ordering = ('workspace_name',)
    inlines = [CalendarInline]
    
    def get_calendars_count(self, obj):
        return obj.mapping_workspace_calendars.count()
    get_calendars_count.short_description = 'Calendars'


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ('agent_id', 'workspace', 'name', 'status', 'voice', 'language', 'get_phone_numbers', 'calendar_configuration', 'created_at')
    list_filter = ('status', 'voice', 'language', 'calendar_configuration', 'created_at')
    search_fields = ('name', 'workspace__workspace_name', 'voice__voice_external_id')
    filter_horizontal = ('phone_numbers',)
    ordering = ('-created_at',)
    
    def get_phone_numbers(self, obj):
        return ", ".join([phone.phonenumber for phone in obj.phone_numbers.all()])
    get_phone_numbers.short_description = 'Phone Numbers'
    
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
        return ", ".join([f"{agent.workspace.workspace_name}" for agent in obj.mapping_agent_phonenumbers.all()])
    get_agents.short_description = 'Agents'


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


@admin.register(Calendar)
class CalendarAdmin(admin.ModelAdmin):
    list_display = ('workspace', 'calendar_type', 'account_id', 'get_configs_count', 'created_at', 'updated_at')
    list_filter = ('calendar_type', 'workspace', 'created_at')
    search_fields = ('workspace__workspace_name', 'account_id', 'calendar_type')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [CalendarConfigurationInline]
    
    def get_configs_count(self, obj):
        return obj.mapping_calendar_configurations.count()
    get_configs_count.short_description = 'Configurations'


@admin.register(CalendarConfiguration)
class CalendarConfigurationAdmin(admin.ModelAdmin):
    list_display = ('get_workspace', 'calendar', 'sub_calendar_id', 'duration', 'prep_time', 'days_buffer', 'from_time', 'to_time')
    list_filter = ('calendar__calendar_type', 'calendar__workspace', 'duration', 'days_buffer', 'created_at')
    search_fields = ('calendar__workspace__workspace_name', 'calendar__account_id', 'sub_calendar_id')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    
    def get_workspace(self, obj):
        return obj.calendar.workspace.workspace_name
    get_workspace.short_description = 'Workspace'
