from rest_framework import serializers
from django.utils import timezone
import uuid


class DocumentUploadSerializer(serializers.Serializer):
    # DB-only like Voices: accept URL and optional metadata
    url = serializers.URLField()
    name = serializers.CharField(required=False, allow_blank=True, max_length=512)
    size = serializers.IntegerField(required=False, min_value=0)


class PresignRequestSerializer(serializers.Serializer):
    download_name = serializers.CharField(required=False, allow_blank=True)


class DocumentInfoSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    size = serializers.IntegerField()
    updated_at = serializers.DateTimeField()
    url = serializers.URLField()


class DocumentListResponseSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    files = DocumentInfoSerializer(many=True)


def build_document_info(agent) -> dict:
    if not agent.kb_doc_id or not agent.kb_doc_url:
        return {}
    return {
        "id": agent.kb_doc_id,
        "name": agent.kb_doc_name or "document.pdf",
        "size": agent.kb_doc_size or 0,
        "updated_at": agent.kb_doc_updated_at or timezone.now(),
        "url": agent.kb_doc_url,
    }


