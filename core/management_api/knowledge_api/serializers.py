from rest_framework import serializers


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField(allow_empty_file=False)


class PresignRequestSerializer(serializers.Serializer):
    download_name = serializers.CharField(required=False, allow_blank=True)


class DocumentInfoSerializer(serializers.Serializer):
    name = serializers.CharField()
    size = serializers.IntegerField()
    updated_at = serializers.DateTimeField()


class DocumentListResponseSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    files = DocumentInfoSerializer(many=True)


