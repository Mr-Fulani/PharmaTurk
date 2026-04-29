from apps.scrapers.services import ScraperIntegrationService


def test_collapse_lcw_media_urls_prefers_larger_image_over_preview():
    service = ScraperIntegrationService()

    urls = [
        "https://img-lcwaikiki.mncdn.com/mnpadding/320/426/ffffff/mpsellerportal/v0/img_101529929v0_c16b1947-bd4f-4426-aa41-28099ba55710.jpg",
        "https://img-lcwaikiki.mncdn.com/mnpadding/1020/1360/ffffff/mpsellerportal/v0/img_101529929v0_c16b1947-bd4f-4426-aa41-28099ba55710.jpg",
        "https://img-lcwaikiki.mncdn.com/mnpadding/320/426/ffffff/mpsellerportal/v0/img_101530339v0_d985c1b9-8a85-4766-af5e-63d7d038e04c.jpg",
        "https://img-lcwaikiki.mncdn.com/mnpadding/1020/1360/ffffff/mpsellerportal/v0/img_101530339v0_d985c1b9-8a85-4766-af5e-63d7d038e04c.jpg",
    ]

    collapsed = service._collapse_lcw_media_urls(urls)

    assert collapsed == [
        "https://img-lcwaikiki.mncdn.com/mnpadding/1020/1360/ffffff/mpsellerportal/v0/img_101529929v0_c16b1947-bd4f-4426-aa41-28099ba55710.jpg",
        "https://img-lcwaikiki.mncdn.com/mnpadding/1020/1360/ffffff/mpsellerportal/v0/img_101530339v0_d985c1b9-8a85-4766-af5e-63d7d038e04c.jpg",
    ]
