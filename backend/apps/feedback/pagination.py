from rest_framework.pagination import PageNumberPagination


class ReviewFeedPagination(PageNumberPagination):
    """Pagination for the mixed platform/product review feed."""

    page_size = 30
    page_size_query_param = "page_size"
    max_page_size = 1000
