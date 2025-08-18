import io
import os
import re
import json
from datetime import datetime, timezone
import uuid
from typing import Dict, Any, Tuple
import logging
import time

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


logger = logging.getLogger(__name__)


def _kb_prefix(agent_id: str) -> str:
    return f"kb/agents/{agent_id}"


def _docs_prefix(agent_id: str) -> str:
    return f"{_kb_prefix(agent_id)}/docs"
def _list_docs(storage: AzureMediaStorage, agent_id: str) -> Tuple[list, str]:
    """List current docs for an agent from storage only (no manifests). Returns (files, prefix)."""
    prefix = _docs_prefix(agent_id)
    dirs, files = ([], [])
    try:
        dirs, files = storage.listdir(prefix)
    except Exception:
        dirs, files = ([], [])
    # Fallback for file-based storage where listdir may not be wired
    if not files:
        try:
            base_path = storage.path(prefix)  # type: ignore[attr-defined]
            if os.path.isdir(base_path):
                files = [f for f in os.listdir(base_path) if os.path.isfile(os.path.join(base_path, f))]
        except Exception:
            pass
    items = []
    for fname in files or []:
        try:
            doc_id = None
            name = fname
            if "__" in fname:
                part, rest = fname.split("__", 1)
                try:
                    uuid.UUID(part)
                    doc_id = part
                    name = rest
                except Exception:
                    # fallback to deterministic id
                    doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"kb/{agent_id}/{fname}"))
            else:
                doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"kb/{agent_id}/{fname}"))
            path = f"{prefix}/{fname}"
            try:
                size = storage.size(path)
            except Exception:
                size = 0
            try:
                mtime = storage.get_modified_time(path)
                updated_at = mtime.isoformat()
            except Exception:
                updated_at = now().isoformat()
            items.append({
                "id": doc_id,
                "name": name,
                "blob_name": fname,
                "size": size,
                "updated_at": updated_at,
            })
        except Exception:
            continue
    return items, prefix


def _retry_until(predicate_fn, attempts: int = 5, delay_seconds: float = 0.15) -> bool:
    """Retry a predicate function a few times with small delay; returns True on success."""
    for _ in range(max(1, attempts)):
        try:
            if predicate_fn():
                return True
        except Exception:
            pass
        time.sleep(max(0.0, delay_seconds))
    return False

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
            storage = AzureMediaStorage()

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
            # Use UUID-based blob name; include docId in filename for easy lookup
            doc_id = str(uuid.uuid4())
            blob_name = f"{doc_id}__{safe_display_name}"
            path = f"{docs_prefix}/{blob_name}"

            # Enforce single-document policy by listing storage
            existing, _ = _list_docs(storage, agent_id)
            if isinstance(existing, list) and len(existing) >= 1:
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

            # Strict consistency verification: blob must exist
            # Retry-based verification to avoid eventual consistency issues
            ok = _retry_until(lambda: storage.exists(path))
            if not ok:
                exc = RuntimeError("kb_consistency_violation_after_post")
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

            files_public = [{
                "id": doc_id,
                "name": safe_display_name,
                "size": size,
                "updated_at": now().isoformat(),
            }]
            return Response({
                "version": 1,
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
        files, _ = _list_docs(storage, agent_id)
        files_public = [{
            "id": f["id"],
            "name": f["name"],
            "size": f.get("size", 0),
            "updated_at": f.get("updated_at"),
        } for f in files]
        return Response({
            "version": 1,
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
        target_id = str(doc_id).lower()
        files, prefix = _list_docs(storage, agent_id)
        entry = next((f for f in files if str(f.get("id")).lower() == target_id), None)
        if not entry:
            raise Http404("File not found")
        path = f"{prefix}/{entry.get('blob_name')}"
        # Delete blob strictly
        try:
            if storage.exists(path):
                storage.delete(path)
            # Verify deletion with small retries
            ok = _retry_until(lambda: (not storage.exists(path)))
            if not ok:
                return Response({"detail": "Storage delete failed.", "code": "kb_storage_delete_failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as exc:
            logger.exception("KB delete: storage error for %s agent %s: %s", path, agent_id, exc)
            return Response({"detail": "Storage delete failed.", "code": "kb_storage_delete_failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Nothing else to update; list-only implementation

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
        target_id = str(doc_id).lower()
        files, prefix = _list_docs(storage, agent_id)
        entry = next((f for f in files if str(f.get("id")).lower() == target_id), None)
        if not entry:
            raise Http404("File not found")
        path = f"{prefix}/{entry.get('blob_name')}"
        if not storage.exists(path):
            raise Http404("File not found")
        try:
            url = storage.url(path)
        except Exception:
            return Response({"detail": "Presign not supported by storage backend."}, status=status.HTTP_501_NOT_IMPLEMENTED)

        return Response({"url": url})


