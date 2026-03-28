from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.users.models import User
from apps.users.telegram_auth import generate_telegram_sync_token
from unittest.mock import patch, MagicMock

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

    @patch('apps.users.telegram_auth.validate_telegram_data')
    def test_telegram_auth_invalid_data(self, mock_validate):
        """Test getting 400 with invalid telegram auth data"""
        mock_validate.return_value = False
        url = reverse('telegram-login')
        response = self.client.post(url, {'id': '123'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('apps.users.telegram_auth.validate_telegram_data')
    def test_telegram_auth_new_user(self, mock_validate):
        """Test creating a new user through telegram auth"""
        mock_validate.return_value = True
        url = reverse('telegram-login')
        payload = {
            'id': '111222333',
            'first_name': 'New',
            'last_name': 'User',
            'username': 'newuser_tg'
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('tokens', response.data)
        
        # Verify user created
        new_user = User.objects.get(telegram_id='111222333')
        self.assertEqual(new_user.first_name, 'New')
        self.assertEqual(new_user.username, 'newuser_tg')
        self.assertTrue(new_user.email.startswith('tg_111222333@'))
        self.assertTrue(new_user.telegram_notifications)

    @patch('apps.users.telegram_auth.validate_telegram_data')
    def test_telegram_auth_existing_user(self, mock_validate):
        """Test logging in an existing user through telegram auth"""
        mock_validate.return_value = True
        # Set telegram id for existing user
        self.user.telegram_id = '999888777'
        self.user.save()
        
        url = reverse('telegram-login')
        payload = {
            'id': '999888777',
            'first_name': 'Updated',
            'username': 'updated_username'
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')
        self.assertEqual(self.user.telegram_username, 'updated_username')


class SocialAuthTests(APITestCase):
    """Тесты OAuth авторизации через Google и VK."""

    def setUp(self):
        self.url = '/api/users/social-auth/'
        self.google_user_info = {
            'provider_id': '117890123456789',
            'email': 'testgoogle@gmail.com',
            'first_name': 'Google',
            'last_name': 'User',
            'avatar_url': 'https://lh3.googleusercontent.com/photo.jpg',
        }
        self.vk_user_info = {
            'provider_id': '123456789',
            'email': None,
            'first_name': 'VK',
            'last_name': 'User',
            'avatar_url': 'https://vk.com/photo.jpg',
        }

    @patch('apps.users.views.PROVIDERS')
    def test_google_auth_new_user(self, mock_providers):
        """Новый пользователь создаётся через Google OAuth."""
        mock_provider = MagicMock()
        mock_provider.return_value.get_user_info.return_value = self.google_user_info
        mock_provider.return_value.id_field = 'google_id'
        mock_provider.return_value.name = 'google'
        mock_providers.get.return_value = mock_provider

        response = self.client.post(self.url, {
            'provider': 'google',
            'access_token': 'fake-google-id-token'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('tokens', response.data)
        self.assertIn('access', response.data['tokens'])

        # Проверяем создание пользователя
        user = User.objects.get(google_id=self.google_user_info['provider_id'])
        self.assertEqual(user.email, self.google_user_info['email'])
        self.assertEqual(user.first_name, 'Google')
        self.assertTrue(user.is_verified)

    @patch('apps.users.views.PROVIDERS')
    def test_google_auth_existing_user_by_google_id(self, mock_providers):
        """Существующий пользователь с google_id просто логинится."""
        existing_user = User.objects.create_user(
            email='existing@gmail.com',
            username='existing_google',
            password='pass123',
            google_id='117890123456789',
        )
        mock_provider = MagicMock()
        mock_provider.return_value.get_user_info.return_value = self.google_user_info
        mock_provider.return_value.id_field = 'google_id'
        mock_provider.return_value.name = 'google'
        mock_providers.get.return_value = mock_provider

        response = self.client.post(self.url, {
            'provider': 'google',
            'access_token': 'fake-token'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Не должен создать нового пользователя
        self.assertEqual(User.objects.filter(google_id='117890123456789').count(), 1)

    @patch('apps.users.views.PROVIDERS')
    def test_google_auth_existing_user_by_email(self, mock_providers):
        """Существующий пользователь с совпадающим email получает google_id."""
        existing = User.objects.create_user(
            email='testgoogle@gmail.com',
            username='existing_by_email',
            password='pass123',
        )
        self.assertFalse(bool(existing.google_id))

        mock_provider = MagicMock()
        mock_provider.return_value.get_user_info.return_value = self.google_user_info
        mock_provider.return_value.id_field = 'google_id'
        mock_provider.return_value.name = 'google'
        mock_providers.get.return_value = mock_provider

        response = self.client.post(self.url, {
            'provider': 'google',
            'access_token': 'fake-token'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        existing.refresh_from_db()
        self.assertEqual(existing.google_id, '117890123456789')

    @patch('apps.users.views.PROVIDERS')
    def test_vk_auth_new_user(self, mock_providers):
        """Новый пользователь создаётся через VK OAuth."""
        mock_provider = MagicMock()
        mock_provider.return_value.get_user_info.return_value = self.vk_user_info
        mock_provider.return_value.id_field = 'vk_id'
        mock_provider.return_value.name = 'vk'
        mock_providers.get.return_value = mock_provider

        response = self.client.post(self.url, {
            'provider': 'vk',
            'access_token': 'fake-vk-token',
            'vk_user_id': '123456789',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user = User.objects.get(vk_id='123456789')
        self.assertEqual(user.first_name, 'VK')
        # У VK нет email — должен быть dummy email
        self.assertIn('@mudaroba.local', user.email)

    def test_social_auth_invalid_provider(self):
        """Неизвестный провайдер возвращает 400."""
        response = self.client.post(self.url, {
            'provider': 'facebook',
            'access_token': 'some-token',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('apps.users.views.PROVIDERS')
    def test_social_auth_provider_failure(self, mock_providers):
        """Если провайдер не смог получить данные (невалидный токен) — возвращает 400."""
        mock_provider = MagicMock()
        mock_provider.return_value.get_user_info.return_value = None  # провайдер вернул None
        mock_provider.return_value.name = 'google'
        mock_providers.get.return_value = mock_provider

        response = self.client.post(self.url, {
            'provider': 'google',
            'access_token': 'invalid-token',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
