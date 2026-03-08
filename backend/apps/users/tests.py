from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.users.models import User
from apps.users.telegram_auth import generate_telegram_sync_token

class TelegramIntegrationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@example.com',
            phone_number='+1234567890',
            password='testpassword123'
        )
        self.client.force_authenticate(user=self.user)

    def test_generate_bind_link(self):
        """Test getting the telegram bind link creates a token"""
        url = '/api/users/profile/telegram-bind-link'
        
        # Test requires authentication
        response = self.client.get(url)
            
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('link', response.data)
        
        # Verify token was saved to user
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.telegram_sync_token)
        self.assertIn(self.user.telegram_sync_token, response.data['link'])

    def test_telegram_webhook_binds_user(self):
        """Test the webhook successfully binds a telegram account"""
        # Create a token manually for the test
        token = generate_telegram_sync_token(self.user)
        
        # Create a mock telegram webhook payload
        payload = {
            "update_id": 123456789,
            "message": {
                "message_id": 1,
                "from": {
                    "id": 987654321,
                    "is_bot": False,
                    "first_name": "Test",
                    "username": "testuser_tg"
                },
                "chat": {
                    "id": 987654321,
                    "type": "private"
                },
                "date": 1618310000,
                "text": f"/start {token}"
            }
        }
        
        # The webhook endpoint should be public
        self.client.logout()
        url = reverse('telegram-webhook')
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify user was updated
        self.user.refresh_from_db()
        self.assertEqual(self.user.telegram_id, '987654321')
        self.assertEqual(self.user.telegram_username, 'testuser_tg')
        self.assertIsNone(self.user.telegram_sync_token)  # Token should be cleared

    def test_telegram_webhook_invalid_token(self):
        """Test webhook with an invalid token"""
        payload = {
            "update_id": 123456789,
            "message": {
                "message_id": 1,
                "from": {
                    "id": 987654321,
                    "first_name": "Test",
                },
                "text": "/start invalid_token"
            }
        }
        
        self.client.logout()
        url = reverse('telegram-webhook')
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # User should not be modified
        self.user.refresh_from_db()
        self.assertIn(self.user.telegram_id, [None, ''])
