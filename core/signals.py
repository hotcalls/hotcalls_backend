from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

from core.models import (
    SubAccount,
    GoogleSubAccount,
    OutlookSubAccount,
    Calendar,
    EventType,
)


def _ensure_router_rows_for_workspace_users(provider: str, provider_subaccount_id: str, workspace):
    """
    Ensure a router SubAccount row exists for every user in the given workspace.
    Safe to call repeatedly due to get_or_create.
    """
    try:
        if not workspace:
            return
        for user in workspace.users.all().only('id'):
            SubAccount.objects.get_or_create(
                owner=user,
                provider=provider,
                sub_account_id=str(provider_subaccount_id),
            )
    except Exception:
        # Non-fatal – router table is a convenience cache
        pass


@receiver(post_save, sender=GoogleSubAccount)
def upsert_router_for_google_subaccount(sender, instance: GoogleSubAccount, created, **kwargs):
    # Create router entries for all workspace members on create; it's idempotent on update
    try:
        workspace = instance.google_calendar.calendar.workspace if instance.google_calendar and instance.google_calendar.calendar else None
        _ensure_router_rows_for_workspace_users('google', str(instance.id), workspace)
    except Exception:
        pass


@receiver(post_save, sender=OutlookSubAccount)
def upsert_router_for_outlook_subaccount(sender, instance: OutlookSubAccount, created, **kwargs):
    try:
        workspace = instance.outlook_calendar.calendar.workspace if instance.outlook_calendar and instance.outlook_calendar.calendar else None
        _ensure_router_rows_for_workspace_users('outlook', str(instance.id), workspace)
    except Exception:
        pass


@receiver(post_delete, sender=GoogleSubAccount)
def delete_router_on_google_subaccount_delete(sender, instance: GoogleSubAccount, **kwargs):
    try:
        SubAccount.objects.filter(provider='google', sub_account_id=str(instance.id)).delete()
    except Exception:
        pass


@receiver(post_delete, sender=OutlookSubAccount)
def delete_router_on_outlook_subaccount_delete(sender, instance: OutlookSubAccount, **kwargs):
    try:
        SubAccount.objects.filter(provider='outlook', sub_account_id=str(instance.id)).delete()
    except Exception:
        pass


@receiver(pre_delete, sender=Calendar)
def revoke_tokens_on_calendar_delete(sender, instance: Calendar, **kwargs):
    """
    Ensure a clean disconnect when a Calendar is deleted via any path (admin
    bulk delete, API, queryset.delete). We revoke provider tokens before the
    rows are removed by cascades.
    """
    try:
        if instance.provider == 'google' and hasattr(instance, 'google_calendar'):
            from core.services.google_calendar import GoogleCalendarService
            try:
                GoogleCalendarService().revoke_tokens(instance.google_calendar)
            except Exception:
                pass
        elif instance.provider == 'outlook' and hasattr(instance, 'outlook_calendar'):
            from core.services.outlook_calendar import OutlookCalendarService
            try:
                OutlookCalendarService().revoke_tokens(instance.outlook_calendar)
            except Exception:
                pass
    except Exception:
        # Never block deletion on revoke errors
        pass


@receiver(post_delete, sender=SubAccount)
def delete_orphan_eventtypes_after_subaccount_delete(sender, instance: SubAccount, **kwargs):
    """
    After a router SubAccount is deleted (typically because its provider
    sub-account was removed when a Calendar was disconnected), remove any
    EventType that now has zero mappings. Working hours cascade via FK.
    """
    try:
        from django.db.models import Count
        orphan_ids = list(
            EventType.objects.annotate(mcount=Count('calendar_mappings')).filter(mcount=0).values_list('id', flat=True)
        )
        if orphan_ids:
            EventType.objects.filter(id__in=orphan_ids).delete()
    except Exception:
        pass


