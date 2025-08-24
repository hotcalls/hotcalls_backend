from __future__ import annotations

from typing import Optional, List, Dict

from django.db import transaction
from django.db.models import Count

from core.models import Workspace, PhoneNumber, WorkspacePhoneNumber


class WorkspacePhoneAssignmentError(Exception):
    pass


@transaction.atomic
def assign_default_number_to_workspace(workspace: Workspace) -> WorkspacePhoneNumber:
    """
    Assign a default phone number to a workspace from the global default pool.

    Selection strategy:
    - Consider PhoneNumber where is_global_default=True and is_active=True
    - Compute current assignment counts in WorkspacePhoneNumber per phone_number
    - Choose the phone(s) with minimal count; break ties deterministically by id
    - Create WorkspacePhoneNumber mapping with is_default=True

    Raises WorkspacePhoneAssignmentError if no eligible global default numbers exist.
    """
    # If already has a default, return it
    existing = (
        WorkspacePhoneNumber.objects.select_for_update()
        .filter(workspace=workspace, is_default=True)
        .first()
    )
    if existing:
        return existing

    eligible_qs = (
        PhoneNumber.objects.select_for_update()
        .filter(is_global_default=True, is_active=True)
    )
    eligible_ids = list(eligible_qs.values_list('id', flat=True))
    if not eligible_ids:
        raise WorkspacePhoneAssignmentError("no_available_default_phone_numbers")

    # Count how many workspaces each eligible number is mapped to
    counts: Dict[str, int] = {str(pid): 0 for pid in eligible_ids}
    agg = (
        WorkspacePhoneNumber.objects
        .filter(phone_number_id__in=eligible_ids)
        .values('phone_number_id')
        .annotate(cnt=Count('id'))
    )
    for row in agg:
        counts[str(row['phone_number_id'])] = int(row['cnt'])

    # Find minimal load
    min_count = min(counts.values()) if counts else 0
    candidates = [pid for pid, c in counts.items() if c == min_count]
    if not candidates:
        # Fallback to all eligible
        candidates = [str(pid) for pid in eligible_ids]

    # Deterministic tie-break by id
    candidates_sorted = sorted(candidates)
    chosen_id = candidates_sorted[0]
    chosen = PhoneNumber.objects.get(id=chosen_id)

    mapping = WorkspacePhoneNumber.objects.create(
        workspace=workspace,
        phone_number=chosen,
        is_default=True,
    )
    return mapping


def get_workspace_default_number(workspace: Workspace) -> Optional[PhoneNumber]:
    mapping = WorkspacePhoneNumber.objects.filter(workspace=workspace, is_default=True).select_related('phone_number').first()
    return mapping.phone_number if mapping else None


def set_workspace_default_number(workspace: Workspace, phone_number: PhoneNumber) -> WorkspacePhoneNumber:
    with transaction.atomic():
        # Ensure mapping exists
        mapping, _ = WorkspacePhoneNumber.objects.get_or_create(
            workspace=workspace, phone_number=phone_number, defaults={'is_default': True}
        )
        if not mapping.is_default:
            mapping.is_default = True
            mapping.save(update_fields=['is_default'])
        # Flip others to False
        WorkspacePhoneNumber.objects.filter(workspace=workspace).exclude(id=mapping.id).update(is_default=False)
        return mapping


