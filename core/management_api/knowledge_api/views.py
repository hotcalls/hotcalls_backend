import logging
import uuid

from django.http import Http404
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter

from core.models import Agent
from .permissions import AgentKnowledgePermission
from .serializers import (
    DocumentUploadSerializer,
    PresignRequestSerializer,
    DocumentListResponseSerializer,
    DocumentInfoSerializer,
    build_document_info,
)

logger = logging.getLogger(__name__)


def _get_agent_or_404(agent_id: str) -> Agent:
    try:
        return Agent.objects.get(agent_id=agent_id)
    except Agent.DoesNotExist:
        raise Http404("Agent not found")


class AgentKnowledgeDocumentsView(APIView):
    permission_classes = [AgentKnowledgePermission]

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

        if agent.kb_doc_id:
            return Response({
                "detail": "Es ist nur ein Dokument erlaubt. Bitte löschen Sie das vorhandene Dokument, bevor Sie ein neues hinzufügen.",
                "code": "kb_single_document_limit",
            }, status=status.HTTP_409_CONFLICT)

        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        url = serializer.validated_data["url"]
        name = serializer.validated_data.get("name") or "document.pdf"
        size = serializer.validated_data.get("size") or 0

        agent.kb_doc_id = uuid.uuid4()
        agent.kb_doc_url = url
        agent.kb_doc_name = name
        agent.kb_doc_size = size
        agent.kb_doc_updated_at = timezone.now()
        agent.save(update_fields=[
            "kb_doc_id", "kb_doc_url", "kb_doc_name", "kb_doc_size", "kb_doc_updated_at"
        ])

        file_info = {
            "id": agent.kb_doc_id,
            "name": agent.kb_doc_name or "document.pdf",
            "size": agent.kb_doc_size or 0,
            "updated_at": agent.kb_doc_updated_at,
            "url": agent.kb_doc_url,
        }
        return Response({
            "version": 1,
            "files": [file_info],
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

        files = []
        if agent.kb_doc_id and agent.kb_doc_url:
            files.append({
                "id": agent.kb_doc_id,
                "name": agent.kb_doc_name or "document.pdf",
                "size": agent.kb_doc_size or 0,
                "updated_at": agent.kb_doc_updated_at or timezone.now(),
                "url": agent.kb_doc_url,
            })
        return Response({"version": 1, "files": files})


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
        # Legacy filename route no longer supported in DB-only mode
        raise Http404("File not found")


class AgentKnowledgeDocumentPresignView(APIView):
    permission_classes = [AgentKnowledgePermission]

    @extend_schema(
        request=PresignRequestSerializer,
        responses={200: {"type": "object"}},
        parameters=[
            OpenApiParameter(name="agent_id", location=OpenApiParameter.PATH, description="Agent UUID", required=True),
            OpenApiParameter(name="filename", location=OpenApiParameter.PATH, description="File name", required=True),
        ],
        tags=["Knowledge"],
        exclude=True,
    )
    def post(self, request, agent_id, filename):
        # Legacy filename route no longer supported in DB-only mode
        raise Http404("File not found")


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
        # No-op in DB-only mode, keep for compatibility
        return Response({"version": 1})


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

        if not agent.kb_doc_id or str(agent.kb_doc_id).lower() != str(doc_id).lower():
            raise Http404("File not found")

        # Clear document fields
        agent.kb_doc_id = None
        agent.kb_doc_url = None
        agent.kb_doc_name = None
        agent.kb_doc_size = None
        agent.kb_doc_updated_at = None
        agent.save(update_fields=[
            "kb_doc_id", "kb_doc_url", "kb_doc_name", "kb_doc_size", "kb_doc_updated_at"
        ])

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

        if not agent.kb_doc_id or str(agent.kb_doc_id).lower() != str(doc_id).lower():
            raise Http404("File not found")

        # Just return the stored URL
        if not agent.kb_doc_url:
            raise Http404("File not found")
        return Response({"url": agent.kb_doc_url})


