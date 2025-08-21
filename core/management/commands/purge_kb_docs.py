import json
from typing import Tuple

from django.core.management.base import BaseCommand
from django.utils.timezone import now

from core.models import Agent
from hotcalls.storage_backends import AzureMediaStorage


def _kb_prefix(agent_id: str) -> str:
    return f"kb/agents/{agent_id}"


def _docs_prefix(agent_id: str) -> str:
    return f"{_kb_prefix(agent_id)}/docs"


def _manifest_path(agent_id: str) -> str:
    return f"{_kb_prefix(agent_id)}/manifest.json"


def _load_manifest(storage: AzureMediaStorage, agent_id: str) -> dict:
    path = _manifest_path(agent_id)
    if not storage.exists(path):
        return {"version": 1, "updated_at": now().isoformat(), "files": []}
    with storage.open(path, "rb") as fh:
        raw = fh.read()
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            # Fallback: reset if unreadable
            return {"version": 1, "updated_at": now().isoformat(), "files": []}


def _save_manifest(storage: AzureMediaStorage, agent_id: str, manifest: dict) -> None:
    manifest["updated_at"] = now().isoformat()
    data = json.dumps(manifest, ensure_ascii=False)
    with storage.open(_manifest_path(agent_id), "wb") as fh:
        fh.write(data.encode("utf-8"))


def _delete_all_docs_for_agent(storage: AzureMediaStorage, agent_id: str) -> Tuple[int, bool]:
    """Delete all blobs under docs prefix and empty manifest. Returns (deleted_file_count, manifest_written)."""
    deleted = 0
    # List files at docs prefix
    prefix = _docs_prefix(agent_id)
    try:
        dirs, files = storage.listdir(prefix)
    except Exception:
        dirs, files = ([], [])

    for fname in files or []:
        try:
            storage.delete(f"{prefix}/{fname}")
            deleted += 1
        except Exception:
            # Continue with best-effort deletion
            continue

    # If there are nested folders, traverse one level deep (Azure may emulate hierarchy)
    for d in dirs or []:
        subdir = f"{prefix}/{d}"
        try:
            _subdirs, subfiles = storage.listdir(subdir)
        except Exception:
            _subdirs, subfiles = ([], [])
        for sf in subfiles or []:
            try:
                storage.delete(f"{subdir}/{sf}")
                deleted += 1
            except Exception:
                continue

    # Reset manifest
    manifest = _load_manifest(storage, agent_id)
    manifest["version"] = int(manifest.get("version", 1)) + 1
    manifest["files"] = []
    _save_manifest(storage, agent_id, manifest)
    return deleted, True


class Command(BaseCommand):
    help = "Purge all Knowledge Base documents for all agents (storage + manifest)."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Confirm deletion of all KB documents")
        parser.add_argument("--dry-run", action="store_true", help="List what would be deleted without changing anything")

    def handle(self, *args, **options):
        if not options.get("yes") and not options.get("dry_run"):
            self.stderr.write(self.style.ERROR("Refusing to delete without --yes or --dry-run."))
            return

        storage = AzureMediaStorage()
        total_deleted = 0
        agents = Agent.objects.all()
        self.stdout.write(self.style.NOTICE(f"Found {agents.count()} agents. Starting purge ({'DRY RUN' if options.get('dry_run') else 'EXECUTE'})..."))

        for agent in agents:
            agent_id = str(agent.agent_id)
            docs_path = _docs_prefix(agent_id)
            if options.get("dry_run"):
                try:
                    dirs, files = storage.listdir(docs_path)
                except Exception:
                    dirs, files = ([], [])
                self.stdout.write(f"Agent {agent_id}: {len(files)} files under {docs_path}")
                continue

            deleted, _ = _delete_all_docs_for_agent(storage, agent_id)
            total_deleted += deleted
            self.stdout.write(f"Agent {agent_id}: deleted {deleted} files and reset manifest")

        if not options.get("dry_run"):
            self.stdout.write(self.style.SUCCESS(f"Completed purge. Total files deleted: {total_deleted}"))
        else:
            self.stdout.write(self.style.WARNING("Dry run completed. No changes were made."))



