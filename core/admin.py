from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Plan, Feature, Workspace, Agent, PhoneNumber, Lead, Blacklist, CallLog


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


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('plan_name', 'created_at', 'updated_at')
    search_fields = ('plan_name',)
    ordering = ('plan_name',)


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ('feature_name', 'plan', 'limit', 'created_at')
    list_filter = ('plan', 'created_at')
    search_fields = ('feature_name', 'plan__plan_name')
    ordering = ('plan', 'feature_name')


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ('workspace_name', 'created_at', 'updated_at')
    search_fields = ('workspace_name',)
    filter_horizontal = ('users',)
    ordering = ('workspace_name',)


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ('agent_id', 'workspace', 'voice', 'language', 'get_phone_numbers', 'created_at')
    list_filter = ('voice', 'language', 'created_at')
    search_fields = ('workspace__workspace_name', 'voice')
    filter_horizontal = ('phone_numbers',)
    ordering = ('-created_at',)
    
    def get_phone_numbers(self, obj):
        return ", ".join([phone.phonenumber for phone in obj.phone_numbers.all()])
    get_phone_numbers.short_description = 'Phone Numbers'


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
    list_display = ('name', 'email', 'phone', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('name', 'email', 'phone')
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
