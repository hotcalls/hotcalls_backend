import io
import os
import re
import json
from datetime import datetime, timezone
import uuid
from typing import Dict, Any, Tuple
import logging

from django.http import Http404
from django.utils.timezone import now
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.core.cache import cache

from core.models import Agent
# Storage backend: prefer Azure in production, but gracefully fallback to local storage in tests/dev
try:
    from hotcalls.storage_backends import AzureMediaStorage  # type: ignore
except Exception:  # pragma: no cover - fallback used in tests without Azure deps
    from django.core.files.storage import FileSystemStorage as AzureMediaStorage  # type: ignore
from .permissions import AgentKnowledgePermission
from .serializers import (
    DocumentUploadSerializer,
    PresignRequestSerializer,
    DocumentListResponseSerializer,
    DocumentInfoSerializer,
)


MANIFEST_NAME = "manifest.json"
logger = logging.getLogger(__name__)


def _kb_prefix(agent_id: str) -> str:
    return f"kb/agents/{agent_id}"


def _docs_prefix(agent_id: str) -> str:
    return f"{_kb_prefix(agent_id)}/docs"


def _manifest_path(agent_id: str) -> str:
    return f"{_kb_prefix(agent_id)}/{MANIFEST_NAME}"


def _load_manifest(storage: AzureMediaStorage, agent_id: str) -> Dict[str, Any]:
    path = _manifest_path(agent_id)
    if not storage.exists(path):
        return {"version": 1, "updated_at": now().isoformat(), "files": []}
    with storage.open(path, "rb") as fh:
        try:
            raw = fh.read()
            data = json.loads(raw.decode("utf-8")) if isinstance(raw, (bytes, bytearray)) else json.loads(raw)
            # Gentle upgrade: ensure blob_name first, then deterministic id
            files = data.get("files", []) or []
            upgraded = False
            new_files = []
            for f in files:
                # Ensure blob_name exists (older manifests may only have name)
                if "blob_name" not in f:
                    f["blob_name"] = f.get("name")
                    upgraded = True

                # Ensure id exists and is stable (deterministic from agent_id + blob_name)
                if "id" not in f or not f.get("id"):
                    try:
                        basis = f.get("blob_name") or f.get("name") or ""
                        deterministic = uuid.uuid5(uuid.NAMESPACE_URL, f"kb/{agent_id}/{basis}")
                        f["id"] = str(deterministic)
                    except Exception:
                        f["id"] = str(uuid.uuid4())
                    upgraded = True
                else:
                    # Normalize id to lowercase string for robust comparisons
                    try:
                        f_id = f.get("id")
                        if f_id is not None:
                            f["id"] = str(f_id).lower()
                    except Exception:
                        pass

                new_files.append(f)
            if upgraded:
                data["files"] = new_files
                try:
                    _save_manifest(storage, agent_id, data)
                except Exception as exc:
                    # Do not fail requests due to upgrade errors; log and continue
                    logger.warning("KB manifest upgrade write failed for agent %s: %s", agent_id, exc)
            return data
        except Exception:
            # fallback: empty manifest if corrupted
            return {"version": 1, "updated_at": now().isoformat(), "files": []}


def _save_manifest(storage: AzureMediaStorage, agent_id: str, manifest: Dict[str, Any]) -> None:
    manifest["updated_at"] = now().isoformat()
    data = json.dumps(manifest, ensure_ascii=False)
    # Write using bytes IO to satisfy storage backend (Azure)
    try:
        # Ensure parent directory exists for local file-based storage backends
        try:
            local_path = storage.path(_manifest_path(agent_id))  # type: ignore[attr-defined]
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
        except Exception:
            pass
        with storage.open(_manifest_path(agent_id), "wb") as fh:
            fh.write(data.encode("utf-8"))
    except Exception:
        # Propagate so caller can handle and return clean JSON error
        raise


def _prune_manifest_or_raise(storage: AzureMediaStorage, agent_id: str) -> Dict[str, Any]:
    """Strictly prune manifest entries whose blobs are missing and persist.

    Returns the updated manifest. Raises on persistence failure.
    """
    manifest = _load_manifest(storage, agent_id)
    files = list(manifest.get("files", []) or [])
    if not files:
        return manifest
    healed_files = []
    changed = False
    for f in files:
        blob = f.get("blob_name") or f.get("name")
        if not blob:
            changed = True
            continue
        path = f"{_docs_prefix(agent_id)}/{blob}"
        try:
            if storage.exists(path):
                healed_files.append(f)
            else:
                changed = True
        except Exception:
            # If exists() fails, do not delete preemptively; keep entry
            healed_files.append(f)
    if changed:
        manifest["files"] = healed_files
        _save_manifest(storage, agent_id, manifest)
    return manifest

def _get_agent_or_404(agent_id: str) -> Agent:
    try:
        return Agent.objects.get(agent_id=agent_id)
    except Agent.DoesNotExist:
        raise Http404("Agent not found")


class AgentKnowledgeDocumentsView(APIView):
    permission_classes = [AgentKnowledgePermission]
    parser_classes = (MultiPartParser, FormParser)

    _MAX_BYTES = 20 * 1024 * 1024  # 20 MB

    @staticmethod
    def _sanitize_filename(original_name: str) -> str:
        # Keep only safe characters; collapse others to '_'
        name = os.path.basename(original_name or "")
        name = name.strip().replace("\\", "_").replace("/", "_")
        name = re.sub(r"[^A-Za-z0-9._\- ]+", "_", name)
        # Avoid empty names
        return name or "document.pdf"

    @staticmethod
    def _is_probable_pdf(uploaded_file) -> bool:
        try:
            pos = uploaded_file.tell()
        except Exception:
            pos = None
        try:
            # Read a small header to detect '%PDF-'
            uploaded_file.seek(0)
            header = uploaded_file.read(5)
            return isinstance(header, (bytes, bytearray)) and header.startswith(b"%PDF-")
        except Exception:
            return False
        finally:
            try:
                if pos is not None:
                    uploaded_file.seek(pos)
            except Exception:
                pass

    @extend_schema(
        request=DocumentUploadSerializer,
        responses={200: DocumentListResponseSerializer},
        parameters=[
            OpenApiParameter(name="agent_id", location=OpenApiParameter.PATH, description="Agent UUID", required=True),
        ],
        tags=["Knowledge"],
    )
    def post(self, request, agent_id):
        agent = _get_agent_or_404(agent_id)
        self.check_object_permissions(request, agent)

        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file = serializer.validated_data["file"]

        # Concurrency lock per agent to avoid race conditions
        lock_key = f"kb:lock:{agent_id}"
        # Increase lock timeout to allow for slower storage writes
        if not cache.add(lock_key, "1", timeout=120):
            return Response({
                "detail": "Ein Upload läuft bereits. Bitte versuchen Sie es in wenigen Sekunden erneut.",
                "code": "kb_upload_in_progress",
            }, status=status.HTTP_409_CONFLICT)

        try:
            # Strictly heal manifest before single-doc policy check
            storage = AzureMediaStorage()
            try:
                _prune_manifest_or_raise(storage, agent_id)
            except Exception as exc:
                logger.exception("KB post: strict manifest heal failed for agent %s: %s", agent_id, exc)
                return Response({
                    "detail": "Manifest write failed.",
                    "code": "kb_manifest_write_failed",
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Size limit pre-check (best-effort)
            if getattr(file, "size", None) is not None and file.size > self._MAX_BYTES:
                return Response({"detail": "File too large. Max 20 MB."}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

            # Always verify PDF magic header
            try:
                file_obj = getattr(file, "file", None) or file
                if not self._is_probable_pdf(file_obj):
                    return Response({"detail": "Invalid PDF content."}, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
            except Exception:
                return Response({"detail": "Unable to read uploaded file."}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

            docs_prefix = _docs_prefix(agent_id)
            original_name = getattr(file, "name", "document.pdf")
            # Sanitize the display name to avoid hidden/unicode separators and unsafe chars
            safe_display_name = self._sanitize_filename(original_name)
            # Use UUID-based blob name to avoid collisions and expensive exists()
            blob_name = f"{uuid.uuid4()}.pdf"
            path = f"{docs_prefix}/{blob_name}"

            # Enforce single-document policy: only one document can be attached per agent
            manifest_existing = _load_manifest(storage, agent_id)
            existing_files = manifest_existing.get("files", [])
            if isinstance(existing_files, list) and len(existing_files) >= 1:
                return Response({
                    "detail": "Es ist nur ein Dokument erlaubt. Bitte löschen Sie das vorhandene Dokument, bevor Sie ein neues hochladen.",
                    "code": "kb_single_document_limit"
                }, status=status.HTTP_409_CONFLICT)

            # Save the uploaded file with streaming size enforcement
            bytes_written = 0
            try:
                # Ensure parent directory exists for local file-based storage backends
                try:
                    local_path = storage.path(path)  # type: ignore[attr-defined]
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                except Exception:
                    pass
                with storage.open(path, "wb") as dest:
                    for chunk in file.chunks():
                        dest.write(chunk)
                        try:
                            bytes_written += len(chunk)
                        except Exception:
                            # Fallback if chunk has no __len__
                            pass
                        if getattr(file, "size", None) is None and bytes_written > self._MAX_BYTES:
                            raise ValueError("file_too_large_stream")
            except ValueError as ve:
                if str(ve) == "file_too_large_stream":
                    try:
                        storage.delete(path)
                    except Exception:
                        pass
                    return Response({"detail": "File too large. Max 20 MB."}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
                # Unexpected ValueError: treat as storage error
                logger.exception("KB upload: unexpected value error for agent %s: %s", agent_id, ve)
                return Response({"detail": "Storage write failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as exc:
                logger.exception("KB upload: failed to write blob to storage for agent %s: %s", agent_id, exc)
                return Response({"detail": "Storage write failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Prefer client-reported size else use streaming count or backend size
            size = getattr(file, "size", None)
            if size is None:
                size = bytes_written
                if not size:
                    try:
                        size = storage.size(path)
                    except Exception:
                        size = 0

            # Update manifest
            manifest = _load_manifest(storage, agent_id)
            manifest["version"] = int(manifest.get("version", 1)) + 1
            # Single-document policy: keep only the new file
            deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"kb/{agent_id}/{blob_name}"))
            manifest["files"] = [{
                "id": deterministic_id,
                "name": safe_display_name,
                "blob_name": blob_name,
                "size": size,
                "updated_at": now().isoformat(),
            }]
            try:
                _save_manifest(storage, agent_id, manifest)
            except Exception as exc:
                # Rollback uploaded blob to keep consistency
                try:
                    storage.delete(path)
                except Exception:
                    pass
                logger.exception("KB upload: failed to write manifest for agent %s: %s", agent_id, exc)
                return Response({"detail": "Manifest write failed.", "code": "kb_manifest_write_failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Strict consistency verification: blob must exist and manifest must contain this file
            try:
                if not storage.exists(path):
                    raise RuntimeError("blob_missing_after_write")
                verify_manifest = _load_manifest(storage, agent_id)
                ids = {str(f.get("id")) for f in (verify_manifest.get("files", []) or [])}
                if deterministic_id not in ids:
                    raise RuntimeError("manifest_missing_new_entry")
            except Exception as exc:
                logger.exception("KB upload: consistency verification failed for agent %s: %s", agent_id, exc)
                # Attempt to cleanup the blob to avoid orphan
                try:
                    storage.delete(path)
                except Exception:
                    pass
                return Response({
                    "detail": "Knowledge Base konnte nicht konsistent gespeichert werden.",
                    "code": "kb_consistency_violation",
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            files_public = []
            for f in manifest.get("files", []) or []:
                files_public.append({
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "size": f.get("size", 0),
                    "updated_at": f.get("updated_at"),
                })
            return Response({
                "version": manifest["version"],
                "files": files_public,
            })
        finally:
            # Release concurrency lock
            try:
                cache.delete(lock_key)
            except Exception:
                pass

    @extend_schema(
        responses={200: DocumentListResponseSerializer},
        parameters=[
            OpenApiParameter(name="agent_id", location=OpenApiParameter.PATH, description="Agent UUID", required=True),
        ],
        tags=["Knowledge"],
    )
    def get(self, request, agent_id):
        agent = _get_agent_or_404(agent_id)
        self.check_object_permissions(request, agent)

        storage = AzureMediaStorage()
        manifest = _load_manifest(storage, agent_id)
        # Auto-heal: prune manifest entries that no longer exist in storage
        try:
            original_files = list(manifest.get("files", []) or [])
            healed_files = []
            changed = False
            for f in original_files:
                blob = f.get("blob_name") or f.get("name")
                if not blob:
                    changed = True
                    continue
                path = f"{_docs_prefix(agent_id)}/{blob}"
                try:
                    if storage.exists(path):
                        healed_files.append(f)
                    else:
                        changed = True
                except Exception:
                    # On storage error assume still exists to avoid false deletion
                    healed_files.append(f)
            if changed:
                manifest["files"] = healed_files
                try:
                    _save_manifest(storage, agent_id, manifest)
                except Exception:
                    # Ignore heal write failure; proceed with in-memory view
                    pass
        except Exception:
            pass
        # Ensure ids are deterministic and stable in responses (in case upgrade couldn't persist)
        files_public = []
        for f in manifest.get("files", []) or []:
            try:
                basis = f.get("blob_name") or f.get("name") or ""
                deterministic = str(uuid.uuid5(uuid.NAMESPACE_URL, f"kb/{agent_id}/{basis}"))
                file_id = (str(f.get("id")) if f.get("id") else deterministic).lower()
            except Exception:
                file_id = str(f.get("id") or uuid.uuid4()).lower()
            files_public.append({
                "id": file_id,
                "name": f.get("name"),
                "size": f.get("size", 0),
                "updated_at": f.get("updated_at"),
            })
        return Response({
            "version": manifest.get("version", 1),
            "files": files_public,
        })


class AgentKnowledgeDocumentDetailView(APIView):
    permission_classes = [AgentKnowledgePermission]

    @extend_schema(
        responses={204: None},
        parameters=[
            OpenApiParameter(name="agent_id", location=OpenApiParameter.PATH, description="Agent UUID", required=True),
            OpenApiParameter(name="filename", location=OpenApiParameter.PATH, description="File name", required=True),
        ],
        tags=["Knowledge"],
        exclude=True,
    )
    def delete(self, request, agent_id, filename):
        agent = _get_agent_or_404(agent_id)
        self.check_object_permissions(request, agent)

        storage = AzureMediaStorage()
        manifest = _load_manifest(storage, agent_id)
        # Try exact filename match via blob_name first
        entry = None
        for f in manifest.get("files", []):
            if f.get("blob_name") == filename or f.get("name") == filename:
                entry = f
                break

        if not entry:
            raise Http404("File not found")

        path = f"{_docs_prefix(agent_id)}/{entry.get('blob_name') or filename}"
        if storage.exists(path):
            storage.delete(path)

        # Update manifest
        manifest["version"] = int(manifest.get("version", 1)) + 1
        # Remove by multiple keys defensively
        def _keep(f):
            try:
                if str(f.get("id")).lower() == str(entry.get("id")).lower():
                    return False
                if (f.get("name") or "") == filename:
                    return False
                if (f.get("blob_name") or "") == filename:
                    return False
                return True
            except Exception:
                return True
        manifest["files"] = [f for f in manifest.get("files", []) if _keep(f)]
        _save_manifest(storage, agent_id, manifest)

        return Response(status=status.HTTP_204_NO_CONTENT)


class AgentKnowledgeDocumentPresignView(APIView):
    permission_classes = [AgentKnowledgePermission]

    @extend_schema(
        request=PresignRequestSerializer,
        responses={200: None},
        parameters=[
            OpenApiParameter(name="agent_id", location=OpenApiParameter.PATH, description="Agent UUID", required=True),
            OpenApiParameter(name="filename", location=OpenApiParameter.PATH, description="File name", required=True),
        ],
        tags=["Knowledge"],
        exclude=True,
    )
    def post(self, request, agent_id, filename):
        agent = _get_agent_or_404(agent_id)
        self.check_object_permissions(request, agent)

        storage = AzureMediaStorage()
        manifest = _load_manifest(storage, agent_id)
        # resolve by blob_name or name
        blob_name = None
        for f in manifest.get("files", []):
            if f.get("blob_name") == filename or f.get("name") == filename:
                blob_name = f.get("blob_name") or filename
                break
        if not blob_name:
            raise Http404("File not found")
        path = f"{_docs_prefix(agent_id)}/{blob_name}"

        # AzureStorage from django-storages does not provide direct presign in all versions.
        # Strategy: Use url() to get an accessible URL if CDN/public, otherwise return 501.
        try:
            if not storage.exists(path):
                raise Http404("File not found")
            url = storage.url(path)
        except Exception:
            return Response({"detail": "Presign not supported by storage backend."}, status=status.HTTP_501_NOT_IMPLEMENTED)

        return Response({
            "url": url,
            # Note: If using SAS tokens, the backend's url() will already include expiry.
        })


class AgentKnowledgeRebuildView(APIView):
    permission_classes = [AgentKnowledgePermission]

    @extend_schema(
        responses={200: {"type": "object"}},
        parameters=[
            OpenApiParameter(name="agent_id", location=OpenApiParameter.PATH, description="Agent UUID", required=True),
        ],
        tags=["Knowledge"],
    )
    def post(self, request, agent_id):
        agent = _get_agent_or_404(agent_id)
        self.check_object_permissions(request, agent)

        storage = AzureMediaStorage()
        manifest = _load_manifest(storage, agent_id)
        manifest["version"] = int(manifest.get("version", 1)) + 1
        _save_manifest(storage, agent_id, manifest)

        return Response({
            "version": manifest["version"],
            "updated_at": manifest["updated_at"],
        })


class AgentKnowledgeDocumentDetailByIdView(APIView):
    permission_classes = [AgentKnowledgePermission]

    @extend_schema(
        responses={204: None},
        parameters=[
            OpenApiParameter(name="agent_id", location=OpenApiParameter.PATH, description="Agent UUID", required=True),
            OpenApiParameter(name="doc_id", location=OpenApiParameter.PATH, description="Document UUID", required=True),
        ],
        tags=["Knowledge"],
    )
    def delete(self, request, agent_id, doc_id):
        agent = _get_agent_or_404(agent_id)
        self.check_object_permissions(request, agent)

        storage = AzureMediaStorage()
        # Heal manifest strictly first
        try:
            manifest = _prune_manifest_or_raise(storage, agent_id)
        except Exception as exc:
            logger.exception("KB delete: strict manifest heal failed for agent %s: %s", agent_id, exc)
            return Response({"detail": "Manifest write failed.", "code": "kb_manifest_write_failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        target_id = str(doc_id).lower()
        # Match by stored id or deterministic id in case manifest id wasn't persisted
        def _matches(f):
            try:
                stored = str(f.get("id", "")).lower()
                basis = f.get("blob_name") or f.get("name") or ""
                deterministic = str(uuid.uuid5(uuid.NAMESPACE_URL, f"kb/{agent_id}/{basis}")).lower()
                return stored == target_id or deterministic == target_id
            except Exception:
                return stored == target_id
        entry = next((f for f in manifest.get("files", []) if _matches(f)), None)
        if not entry:
            raise Http404("File not found")

        path = f"{_docs_prefix(agent_id)}/{entry.get('blob_name') or entry.get('name')}"
        # Delete blob strictly
        try:
            if storage.exists(path):
                storage.delete(path)
            # Verify deletion
            if storage.exists(path):
                return Response({"detail": "Storage delete failed.", "code": "kb_storage_delete_failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as exc:
            logger.exception("KB delete: storage error for %s agent %s: %s", path, agent_id, exc)
            return Response({"detail": "Storage delete failed.", "code": "kb_storage_delete_failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        manifest["version"] = int(manifest.get("version", 1)) + 1
        # Remove by robust matching (id or deterministic id)
        def _keep(f):
            try:
                stored = str(f.get("id", "")).lower()
                basis = f.get("blob_name") or f.get("name") or ""
                deterministic = str(uuid.uuid5(uuid.NAMESPACE_URL, f"kb/{agent_id}/{basis}")).lower()
                return not (stored == target_id or deterministic == target_id)
            except Exception:
                return str(f.get("id")) != str(doc_id)
        manifest["files"] = [f for f in manifest.get("files", []) if _keep(f)]
        try:
            _save_manifest(storage, agent_id, manifest)
        except Exception as exc:
            logger.exception("KB delete: manifest save failed for agent %s: %s", agent_id, exc)
            return Response({"detail": "Manifest write failed.", "code": "kb_manifest_write_failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Verify manifest does not include target entry anymore
        verify_manifest = _load_manifest(storage, agent_id)
        for f in verify_manifest.get("files", []) or []:
            try:
                stored = str(f.get("id", "")).lower()
                basis = f.get("blob_name") or f.get("name") or ""
                deterministic = str(uuid.uuid5(uuid.NAMESPACE_URL, f"kb/{agent_id}/{basis}")).lower()
                if stored == target_id or deterministic == target_id:
                    return Response({"detail": "Manifest still contains entry.", "code": "kb_consistency_violation"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception:
                continue

        return Response(status=status.HTTP_204_NO_CONTENT)


class AgentKnowledgeDocumentPresignByIdView(APIView):
    permission_classes = [AgentKnowledgePermission]

    @extend_schema(
        request=PresignRequestSerializer,
        responses={200: {"type": "object"}},
        parameters=[
            OpenApiParameter(name="agent_id", location=OpenApiParameter.PATH, description="Agent UUID", required=True),
            OpenApiParameter(name="doc_id", location=OpenApiParameter.PATH, description="Document UUID", required=True),
        ],
        tags=["Knowledge"],
    )
    def post(self, request, agent_id, doc_id):
        agent = _get_agent_or_404(agent_id)
        self.check_object_permissions(request, agent)

        storage = AzureMediaStorage()
        manifest = _load_manifest(storage, agent_id)
        target_id = str(doc_id).lower()
        def _matches(f):
            try:
                stored = str(f.get("id", "")).lower()
                basis = f.get("blob_name") or f.get("name") or ""
                deterministic = str(uuid.uuid5(uuid.NAMESPACE_URL, f"kb/{agent_id}/{basis}")).lower()
                return stored == target_id or deterministic == target_id
            except Exception:
                return stored == target_id
        entry = next((f for f in manifest.get("files", []) if _matches(f)), None)
        if not entry:
            raise Http404("File not found")

        path = f"{_docs_prefix(agent_id)}/{entry.get('blob_name') or entry.get('name')}"
        if not storage.exists(path):
            raise Http404("File not found")
        try:
            url = storage.url(path)
        except Exception:
            return Response({"detail": "Presign not supported by storage backend."}, status=status.HTTP_501_NOT_IMPLEMENTED)

        return Response({"url": url})


