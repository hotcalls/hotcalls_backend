from django.urls import path
from . import views

urlpatterns = [
    # Upload a PDF to an agent's knowledge base
    path(
        'agents/<uuid:agent_id>/documents/',
        views.AgentKnowledgeDocumentsView.as_view(),
        name='agent-knowledge-documents'
    ),
    # Delete a specific PDF
    path(
        'agents/<uuid:agent_id>/documents/<str:filename>/',
        views.AgentKnowledgeDocumentDetailView.as_view(),
        name='agent-knowledge-document-detail'
    ),
    # Create a short-lived presigned URL for a specific PDF
    path(
        'agents/<uuid:agent_id>/documents/<str:filename>/presign/',
        views.AgentKnowledgeDocumentPresignView.as_view(),
        name='agent-knowledge-document-presign'
    ),
    # Optional explicit rebuild trigger to bump manifest version
    path(
        'agents/<uuid:agent_id>/rebuild/',
        views.AgentKnowledgeRebuildView.as_view(),
        name='agent-knowledge-rebuild'
    ),
]


