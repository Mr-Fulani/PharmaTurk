"""Views для API страницы Page.

View `PageDetailView` возвращает JSON с локализованными полями. Язык выбирается через GET-параметр `lang` (например, ?lang=ru).
"""

from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework import status
from .models import Page
from .serializers import PageSerializer


class PageListView(generics.ListAPIView):
    """Возвращает список активных страниц.
    
    Может быть отфильтрован через ?show_in_footer=1
    """
    queryset = Page.objects.filter(is_active=True)
    serializer_class = PageSerializer
    permission_classes = [permissions.AllowAny]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        lang = (
            self.request.GET.get("lang")
            or self.request.GET.get("locale")
            or self.request.headers.get("X-Language", "").split("-")[0].lower() or "ru"
        )
        context["lang"] = lang
        return context

    def get_queryset(self):
        """Возвращает только активные страницы."""
        return Page.objects.filter(is_active=True).order_by("footer_order", "-updated_at")


class PageDetailView(generics.RetrieveAPIView):
    """Возвращает данные страницы по её slug.

    Public endpoint: доступен всем (permissions.AllowAny). При отсутствии объекта возвращается 404.
    Поддерживает GET-параметр `lang` для выбора языка (ru/en).
    """

    queryset = Page.objects.all()
    serializer_class = PageSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"

    def get(self, request, *args, **kwargs):
        # Определяем язык: ?lang=, ?locale=, заголовок X-Language, иначе default 'ru'
        lang = (
            request.GET.get("lang")
            or request.GET.get("locale")
            or request.GET.get("_lang")
            or request.headers.get("X-Language", "").split("-")[0].lower() or "ru"
        )
        self.serializer_class = PageSerializer
        try:
            page = self.get_object()
        except Exception:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(page, context={"lang": lang})
        return Response(serializer.data)
