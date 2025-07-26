from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Plan, Feature, PlanFeature, Workspace, Agent, PhoneNumber, Lead, Blacklist, CallLog, 
    Calendar, CalendarConfiguration, GoogleCalendarConnection, GoogleCalendar
)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """Custom admin for User model"""
    list_display = ('username', 'email', 'phone', 'status', 'is_staff', 'date_joined')
    list_filter = ('status', 'is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'phone')
    ordering = ('-date_joined',)
    
    # Add custom fields to the fieldsets
    fieldsets = UserAdmin.fieldsets + (
        ('Custom Fields', {
            'fields': ('phone', 'stripe_customer_id', 'status', 'social_id', 'social_provider')
        }),
    )
    
    # Add custom fields to add form
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Custom Fields', {
            'fields': ('phone', 'stripe_customer_id', 'status', 'social_id', 'social_provider')
        }),
    )


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


class GoogleCalendarInline(admin.TabularInline):
    model = GoogleCalendar
    extra = 0
    fields = ('external_id', 'summary', 'primary', 'access_role', 'time_zone')
    readonly_fields = ('external_id', 'summary', 'primary', 'access_role', 'time_zone', 'created_at', 'updated_at')


class CalendarInline(admin.TabularInline):
    model = Calendar
    extra = 0
    fields = ('name', 'provider', 'active')
    readonly_fields = ('created_at', 'updated_at')


class CalendarConfigurationInline(admin.TabularInline):
    model = CalendarConfiguration
    extra = 0
    fields = ('duration', 'prep_time', 'days_buffer', 'from_time', 'to_time')


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
    list_display = ('workspace_name', 'get_calendars_count', 'get_google_connections_count', 'created_at', 'updated_at')
    search_fields = ('workspace_name',)
    filter_horizontal = ('users',)
    ordering = ('workspace_name',)
    inlines = [CalendarInline]
    
    def get_calendars_count(self, obj):
        return obj.calendars.count()
    get_calendars_count.short_description = 'Calendars'
    
    def get_google_connections_count(self, obj):
        return obj.google_calendar_connections.filter(active=True).count()
    get_google_connections_count.short_description = 'Google Connections'


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ('agent_id', 'workspace', 'voice', 'language', 'get_phone_numbers', 'calendar_configuration', 'created_at')
    list_filter = ('voice', 'language', 'calendar_configuration', 'created_at')
    search_fields = ('workspace__workspace_name', 'voice')
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
    search_fields = ('user__username', 'user__email', 'reason')
    ordering = ('-created_at',)


@admin.register(CallLog)
class CallLogAdmin(admin.ModelAdmin):
    list_display = ('lead', 'from_number', 'to_number', 'direction', 'duration', 'timestamp')
    list_filter = ('direction', 'timestamp', 'disconnection_reason')
    search_fields = ('lead__name', 'from_number', 'to_number')
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
    list_display = ('summary', 'get_workspace', 'connection', 'primary', 'access_role', 'selected')
    list_filter = ('primary', 'access_role', 'selected', 'connection__workspace', 'created_at')
    search_fields = ('summary', 'external_id', 'connection__account_email', 'connection__workspace__workspace_name')
    ordering = ('-created_at',)
    readonly_fields = ('external_id', 'etag', 'kind', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Calendar Info', {
            'fields': ('calendar', 'connection', 'external_id', 'summary', 'description')
        }),
        ('Visual Properties', {
            'fields': ('color_id', 'background_color', 'foreground_color'),
            'classes': ('collapse',)
        }),
        ('Calendar Properties', {
            'fields': ('primary', 'access_role', 'time_zone', 'selected')
        }),
        ('Google API Metadata', {
            'fields': ('etag', 'kind'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_workspace(self, obj):
        return obj.connection.workspace.workspace_name
    get_workspace.short_description = 'Workspace'


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
            connection = obj.google_calendar.connection
            if not connection.active:
                return '❌ Disconnected'
            elif connection.sync_errors:
                return '⚠️ Errors'
            else:
                return '✅ Connected'
        return '❓ Unknown'
    get_connection_status.short_description = 'Status'


@admin.register(CalendarConfiguration)
class CalendarConfigurationAdmin(admin.ModelAdmin):
    list_display = ('get_workspace', 'get_calendar_name', 'get_provider', 'duration', 'prep_time', 'days_buffer', 'from_time', 'to_time')
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
