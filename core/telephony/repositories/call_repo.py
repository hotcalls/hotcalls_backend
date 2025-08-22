from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from django.db import transaction

from core.models import CallTask


@contextmanager
def lock_call_task(call_task_id: str) -> Iterator[CallTask]:
    """
    Obtain a row lock on CallTask to ensure idempotency when placing calls.
    """
    with transaction.atomic():
        task = CallTask.objects.select_for_update().get(id=call_task_id)
        yield task




