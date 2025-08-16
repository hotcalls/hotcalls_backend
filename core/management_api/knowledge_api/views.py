import io
import os
import re
import json
from datetime import datetime, timezone
from typing import Dict, Any, Tuple

from django.http import Http404
from django.utils.timezone import now
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from drf_spectacular.utils import extend_schema, OpenApiParameter

from core.models import Agent
from hotcalls.storage_backends import AzureMediaStorage
from .permissions import AgentKnowledgePermission
from .serializers import (
    DocumentUploadSerializer,
    PresignRequestSerializer,
    DocumentListResponseSerializer,
    DocumentInfoSerializer,
)


MANIFEST_NAME = "manifest.json"


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
    with storage.open(path, "r") as fh:
        try:
            return json.load(fh)
        except Exception:
            # fallback: empty manifest if corrupted
            return {"version": 1, "updated_at": now().isoformat(), "files": []}


def _save_manifest(storage: AzureMediaStorage, agent_id: str, manifest: Dict[str, Any]) -> None:
    manifest["updated_at"] = now().isoformat()
    data = json.dumps(manifest, ensure_ascii=False)
    # Write using bytes IO to satisfy storage backend
    with storage.open(_manifest_path(agent_id), "w") as fh:
        fh.write(data)


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

        # Size limit
        if getattr(file, "size", None) is not None and file.size > self._MAX_BYTES:
            return Response({"detail": "File too large. Max 20 MB."}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

        # Content type / magic sniff: accept application/pdf or octet-stream with PDF header
        content_type = getattr(file, "content_type", "") or ""
        if content_type not in ("application/pdf", "application/octet-stream"):
            return Response({"detail": "Only PDF files are allowed."}, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
        # If octet-stream, try magic check
        try:
            file_obj = getattr(file, "file", None) or file
            if content_type != "application/pdf" and not self._is_probable_pdf(file_obj):
                return Response({"detail": "Invalid PDF content."}, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
        except Exception:
            return Response({"detail": "Unable to read uploaded file."}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        storage = AzureMediaStorage()
        docs_prefix = _docs_prefix(agent_id)
        filename = self._sanitize_filename(getattr(file, "name", "document.pdf"))
        path = f"{docs_prefix}/{filename}"

        if storage.exists(path):
            return Response({"detail": "File already exists."}, status=status.HTTP_409_CONFLICT)

        # Enforce single-document policy: only one document can be attached per agent
        manifest_existing = _load_manifest(storage, agent_id)
        existing_files = manifest_existing.get("files", [])
        if isinstance(existing_files, list) and len(existing_files) >= 1:
            return Response({
                "detail": "Es ist nur ein Dokument erlaubt. Bitte löschen Sie das vorhandene Dokument, bevor Sie ein neues hochladen.",
                "code": "kb_single_document_limit"
            }, status=status.HTTP_409_CONFLICT)

        # Save the uploaded file
        with storage.open(path, "wb") as dest:
            for chunk in file.chunks():
                dest.write(chunk)

        size = storage.size(path)

        # Update manifest
        manifest = _load_manifest(storage, agent_id)
        manifest["version"] = int(manifest.get("version", 1)) + 1
        # Remove existing entry with same name if any
        manifest["files"] = [f for f in manifest.get("files", []) if f.get("name") != filename]
        manifest["files"].append({
            "name": filename,
            "size": size,
            "updated_at": now().isoformat(),
        })
        _save_manifest(storage, agent_id, manifest)

        return Response({
            "version": manifest["version"],
            "files": manifest["files"],
        })

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
        return Response({
            "version": manifest.get("version", 1),
            "files": manifest.get("files", []),
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
    )
    def delete(self, request, agent_id, filename):
        agent = _get_agent_or_404(agent_id)
        self.check_object_permissions(request, agent)

        storage = AzureMediaStorage()
        path = f"{_docs_prefix(agent_id)}/{filename}"

        if not storage.exists(path):
            raise Http404("File not found")

        storage.delete(path)

        # Update manifest
        manifest = _load_manifest(storage, agent_id)
        manifest["version"] = int(manifest.get("version", 1)) + 1
        manifest["files"] = [f for f in manifest.get("files", []) if f.get("name") != filename]
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
    )
    def post(self, request, agent_id, filename):
        agent = _get_agent_or_404(agent_id)
        self.check_object_permissions(request, agent)

        storage = AzureMediaStorage()
        path = f"{_docs_prefix(agent_id)}/{filename}"
        if not storage.exists(path):
            raise Http404("File not found")

        # AzureStorage from django-storages does not provide direct presign in all versions.
        # Strategy: Use url() to get an accessible URL if CDN/public, otherwise return 501.
        try:
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


