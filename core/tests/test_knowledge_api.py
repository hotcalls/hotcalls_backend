import io
import uuid
from unittest.mock import patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import FileSystemStorage
from django.test import override_settings
from rest_framework import status

from core.tests.base import BaseAPITestCase


class LocalMediaStorage:
    """
    Minimal local storage that mimics the subset of AzureMediaStorage used by views.
    Delegates to FileSystemStorage in tests' MEDIA_ROOT.
    """

    def __init__(self, *args, **kwargs):
        self._fs = FileSystemStorage(location=settings.MEDIA_ROOT)

    def open(self, name, mode='rb'):
        # Ensure parent directories exist are handled by FileSystemStorage
        return self._fs.open(name, mode)

    def exists(self, name):
        return self._fs.exists(name)

    def delete(self, name):
        try:
            return self._fs.delete(name)
        except FileNotFoundError:
            return False

    def size(self, name):
        return self._fs.size(name)

    def url(self, name):
        # Return a deterministic local URL for tests
        return self._fs.url(name)

    def path(self, name):
        return self._fs.path(name)


@override_settings(DEFAULT_FILE_STORAGE='django.core.files.storage.FileSystemStorage')
class KnowledgeApiTests(BaseAPITestCase):
    base_endpoint = '/api/knowledge/agents/{agent_id}/documents/'

    def setUp(self):
        super().setUp()
        # Create agent and ensure regular user is member of its workspace
        self.agent = self.create_test_agent()
        self.agent.workspace.users.add(self.regular_user)

    def _pdf(self, name='doc.pdf', size_bytes=1024):
        # Create a minimal PDF-like content starting with %PDF-
        content = b'%PDF-1.4\n' + b'0' * max(0, size_bytes - 8)
        return SimpleUploadedFile(name, content, content_type='application/pdf')

    def _non_pdf(self, name='doc.txt', size_bytes=128):
        content = b'This is not a pdf.' + b'0' * max(0, size_bytes - 20)
        return SimpleUploadedFile(name, content, content_type='text/plain')

    def _url(self, agent_id=None):
        return self.base_endpoint.format(agent_id=str(agent_id or self.agent.agent_id))

    @patch('core.management_api.knowledge_api.views.AzureMediaStorage', new=LocalMediaStorage)
    def test_list_empty(self):
        resp = self.user_client.get(self._url())
        self.assert_response_success(resp, expected_status=status.HTTP_200_OK)
        self.assertIn('version', resp.data)
        self.assertIn('files', resp.data)
        self.assertEqual(resp.data['files'], [])

    @patch('core.management_api.knowledge_api.views.AzureMediaStorage', new=LocalMediaStorage)
    def test_upload_pdf_and_list(self):
        file = self._pdf('My File.pdf', 4096)
        resp = self.user_client.post(self._url(), data={'file': file}, format='multipart')
        self.assert_response_success(resp)
        self.assertIn('files', resp.data)
        self.assertEqual(len(resp.data['files']), 1)
        item = resp.data['files'][0]
        self.assertIn('id', item)
        self.assertIn('name', item)
        self.assertIn('size', item)
        self.assertIn('updated_at', item)
        # Name should be sanitized (no dangerous chars)
        self.assertTrue(item['name'].endswith('.pdf'))

        # GET should reflect same single-document state
        resp2 = self.user_client.get(self._url())
        self.assert_response_success(resp2)
        self.assertEqual(len(resp2.data['files']), 1)

    @patch('core.management_api.knowledge_api.views.AzureMediaStorage', new=LocalMediaStorage)
    def test_upload_rejects_non_pdf(self):
        file = self._non_pdf('evil.txt', 256)
        resp = self.user_client.post(self._url(), data={'file': file}, format='multipart')
        self.assert_response_error(resp, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

    @patch('core.management_api.knowledge_api.views.AzureMediaStorage', new=LocalMediaStorage)
    def test_upload_rejects_too_large(self):
        # Create a 21MB PDF
        size_bytes = 21 * 1024 * 1024
        file = self._pdf('big.pdf', size_bytes)
        resp = self.user_client.post(self._url(), data={'file': file}, format='multipart')
        self.assert_response_error(resp, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

    @patch('core.management_api.knowledge_api.views.AzureMediaStorage', new=LocalMediaStorage)
    def test_single_document_limit(self):
        f1 = self._pdf('a.pdf', 2048)
        resp1 = self.user_client.post(self._url(), data={'file': f1}, format='multipart')
        self.assert_response_success(resp1)
        f2 = self._pdf('b.pdf', 2048)
        resp2 = self.user_client.post(self._url(), data={'file': f2}, format='multipart')
        self.assert_response_error(resp2, status.HTTP_409_CONFLICT)
        self.assertEqual(resp2.data.get('code'), 'kb_single_document_limit')

    @patch('core.management_api.knowledge_api.views.AzureMediaStorage', new=LocalMediaStorage)
    def test_delete_by_id(self):
        upload = self.user_client.post(self._url(), data={'file': self._pdf('x.pdf')}, format='multipart')
        self.assert_response_success(upload)
        doc_id = upload.data['files'][0]['id']
        url = f"/api/knowledge/agents/{self.agent.agent_id}/documents/by-id/{doc_id}/"
        resp = self.user_client.delete(url)
        self.assert_delete_success(resp)
        # Now list should be empty
        resp2 = self.user_client.get(self._url())
        self.assert_response_success(resp2)
        self.assertEqual(resp2.data['files'], [])

    @patch('core.management_api.knowledge_api.views.AzureMediaStorage', new=LocalMediaStorage)
    def test_presign_by_id(self):
        upload = self.user_client.post(self._url(), data={'file': self._pdf('k.pdf')}, format='multipart')
        self.assert_response_success(upload)
        doc_id = upload.data['files'][0]['id']
        url = f"/api/knowledge/agents/{self.agent.agent_id}/documents/by-id/{doc_id}/presign/"
        resp = self.user_client.post(url, data={})
        self.assert_response_success(resp)
        self.assertIn('url', resp.data)
        self.assertTrue(isinstance(resp.data['url'], str))

    @patch('core.management_api.knowledge_api.views.AzureMediaStorage', new=LocalMediaStorage)
    def test_permissions_denied_for_non_member(self):
        # Remove user from workspace members
        self.agent.workspace.users.remove(self.regular_user)
        resp = self.user_client.get(self._url())
        self.assert_response_error(resp, status.HTTP_403_FORBIDDEN)

    @patch('core.management_api.knowledge_api.views.AzureMediaStorage', new=LocalMediaStorage)
    def test_staff_bypass_permissions(self):
        resp = self.staff_client.get(self._url())
        self.assert_response_success(resp)

    @patch('core.management_api.knowledge_api.views.AzureMediaStorage', new=LocalMediaStorage)
    def test_agent_not_found(self):
        fake_id = uuid.uuid4()
        url = self.base_endpoint.format(agent_id=str(fake_id))
        resp = self.user_client.get(url)
        self.assert_response_error(resp, status.HTTP_404_NOT_FOUND)


