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
import requests
import json
from openai import OpenAI

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
        if not cache.add(lock_key, "1", timeout=120):
            return Response({
                "detail": "Ein Upload läuft bereits. Bitte versuchen Sie es in wenigen Sekunden erneut.",
                "code": "kb_upload_in_progress",
            }, status=status.HTTP_409_CONFLICT)

        try:
            # Size limit pre-check (best-effort)
            if getattr(file, "size", None) is not None and file.size > self._MAX_BYTES:
                return Response({"detail": "File too large. Max 20 MB."}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

            # Verify PDF magic header
            try:
                file_obj = getattr(file, "file", None) or file
                if not self._is_probable_pdf(file_obj):
                    return Response({"detail": "Invalid PDF content."}, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
            except Exception:
                return Response({"detail": "Unable to read uploaded file."}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

            # Assign like voices to FileField (auto handles storage)
            original_name = getattr(file, "name", "document.pdf")
            safe_display_name = self._sanitize_filename(original_name)
            file.name = safe_display_name

            # Enforce single-document policy by replacing existing
            if agent.kb_pdf:
                try:
                    agent.kb_pdf.delete(save=False)
                except Exception:
                    pass
            agent.kb_pdf = file
            agent.save(update_fields=['kb_pdf', 'updated_at'])

            # After storing the PDF, synchronously generate a verbatim text via OpenAI Vision
            try:
                # Resolve actual stored path and URL for the PDF (use FileField path)
                storage = AzureMediaStorage()
                try:
                    pdf_path = agent.kb_pdf.name  # already includes upload_to path
                except Exception:
                    pdf_path = None
                try:
                    pdf_url = storage.url(pdf_path) if pdf_path else None
                except Exception:
                    pdf_url = None

                openai_api_key = os.getenv('OPENAI_API_KEY')
                model = os.getenv('KNOWLEDGE_VISION_MODEL', 'gpt-4o')
                if openai_api_key:
                    try:
                        client = OpenAI(api_key=openai_api_key)
                        # Upload PDF bytes directly to OpenAI as user_data
                        with storage.open(agent.kb_pdf.name, "rb") as fh:
                            up = client.files.create(file=fh, purpose="user_data")

                        # Ask vision-capable model to extract full plain text
                        resp = client.responses.create(
                            model=model,
                            temperature=0,
                            input=[{
                                "role": "user",
                                "content": [
                                    {
                                        "type": "input_text",
                                        "text": (
                                            "Extract the full plain text from this PDF. "
                                            "Preserve reading order, merge hyphenated line breaks, "
                                            "and render tables as TSV (tab-separated). Output ONLY text."
                                        )
                                    },
                                    {"type": "input_file", "file_id": up.id},
                                ],
                            }],
                        )
                        text = getattr(resp, "output_text", None) or ""

                        # Save .txt next to the PDF
                        try:
                            base_no_ext = os.path.splitext(os.path.basename(pdf_path or safe_display_name))[0]
                            dir_path = os.path.dirname(pdf_path) if pdf_path else _docs_prefix(agent_id)
                            txt_path = f"{dir_path}/{base_no_ext}.txt"
                            with storage.open(txt_path, "wb") as fh:
                                fh.write(text.encode("utf-8"))
                        except Exception as write_exc:
                            logger.warning("KB: failed to write txt for %s: %s", agent_id, write_exc)
                    except Exception as ocr_exc:
                        logger.warning("KB: OpenAI OCR failed for %s: %s", agent_id, ocr_exc)
                else:
                    logger.warning("KB: OPENAI_API_KEY not set; skipping OCR")
            except Exception as vision_exc:
                logger.warning("KB: Vision OCR failed for %s: %s", agent_id, vision_exc)

            # Response format compatible with frontend (single file list)
            try:
                size_val = getattr(agent.kb_pdf, 'size', None)
            except Exception:
                size_val = None
            size_val = size_val or 0

            files_public = [{
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"kb/{agent.agent_id}/{safe_display_name}")),
                "name": safe_display_name,
                "size": size_val,
                "updated_at": now().isoformat(),
            }]
            return Response({
                "version": 1,
                "files": files_public,
            })
        finally:
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

        files_public = []
        if agent.kb_pdf:
            name = os.path.basename(agent.kb_pdf.name)
            try:
                size_val = agent.kb_pdf.size
            except Exception:
                size_val = 0
            files_public.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"kb/{agent.agent_id}/{name}")),
                "name": name,
                "size": size_val or 0,
                "updated_at": now().isoformat(),
            })
        return Response({
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

        if not agent.kb_pdf:
            raise Http404("File not found")

        current_name = os.path.basename(agent.kb_pdf.name)
        deterministic = uuid.uuid5(uuid.NAMESPACE_URL, f"kb/{agent.agent_id}/{current_name}")
        if str(deterministic) != str(doc_id):
            raise Http404("File not found")

        try:
            agent.kb_pdf.delete(save=False)
        except Exception:
            pass
        agent.kb_pdf = None
        agent.save(update_fields=['kb_pdf', 'updated_at'])

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
                return False

        entry = next((f for f in manifest.get("files", []) if _matches(f)), None)

        url = None
        text_url = None

        if entry:
            path = f"{_docs_prefix(agent_id)}/{entry.get('blob_name') or entry.get('name')}"
            if not storage.exists(path):
                raise Http404("File not found")
            try:
                url = storage.url(path)
            except Exception:
                return Response({"detail": "Presign not supported by storage backend."}, status=status.HTTP_501_NOT_IMPLEMENTED)

            try:
                base_no_ext = os.path.splitext(os.path.basename(path))[0]
                txt_path = f"{os.path.dirname(path)}/{base_no_ext}.txt"
                if storage.exists(txt_path):
                    text_url = storage.url(txt_path)
            except Exception:
                pass
        else:
            # Fallback: single-file mode using agent.kb_pdf
            if not agent.kb_pdf:
                raise Http404("File not found")
            current_name = os.path.basename(agent.kb_pdf.name)
            deterministic = uuid.uuid5(uuid.NAMESPACE_URL, f"kb/{agent.agent_id}/{current_name}")
            if str(deterministic) != str(doc_id):
                raise Http404("File not found")
            path = agent.kb_pdf.name
            if not storage.exists(path):
                raise Http404("File not found")
            try:
                url = storage.url(path)
            except Exception:
                return Response({"detail": "Presign not supported by storage backend."}, status=status.HTTP_501_NOT_IMPLEMENTED)
            try:
                base_no_ext = os.path.splitext(current_name)[0]
                txt_path = f"{os.path.dirname(path)}/{base_no_ext}.txt"
                if storage.exists(txt_path):
                    text_url = storage.url(txt_path)
            except Exception:
                pass

        out = {"url": url}
        if text_url:
            out["text_url"] = text_url
        return Response(out)


