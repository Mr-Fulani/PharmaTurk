import io
from unittest import mock
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile


class TempImageUploadTests(APITestCase):
    def setUp(self):
        self.url = reverse("temp-upload")

    def _generate_valid_image(self):
        file = io.BytesIO()
        image = Image.new("RGB", size=(100, 100), color=(255, 0, 0))
        image.save(file, "jpeg")
        file.name = "test.jpg"
        file.seek(0)
        return SimpleUploadedFile("test.jpg", file.read(), content_type="image/jpeg")

    def test_upload_valid_image(self):
        image = self._generate_valid_image()
        response = self.client.post(self.url, {"file": image}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("url", response.data)

    def test_upload_missing_file(self):
        response = self.client.post(self.url, {}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_invalid_file_type(self):
        # Text file pretending to be an image
        bad_file = SimpleUploadedFile("fake.jpg", b"not an image", content_type="image/jpeg")
        response = self.client.post(self.url, {"file": bad_file}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_upload_file_too_large(self):
        # Generate a valid image, but pad it with dummy data to make it larger than 5MB
        file = io.BytesIO()
        image = Image.new("RGB", size=(100, 100), color=(255, 0, 0))
        image.save(file, "jpeg")
        # Pad file to 6MB
        file.write(b"0" * (6 * 1024 * 1024))
        file.seek(0)
        
        large_image = SimpleUploadedFile("large.jpg", file.read(), content_type="image/jpeg")
        
        response = self.client.post(
            self.url, 
            {"file": large_image}, 
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("size", str(response.data.get("error", "")).lower())
