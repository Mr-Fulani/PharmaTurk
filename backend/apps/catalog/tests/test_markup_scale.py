from decimal import Decimal

import pytest
from django.urls import reverse

from apps.catalog.currency_models import MarkupScale, MarkupScaleStep
from apps.catalog.utils.markup_scale import apply_scale, scale_examples


STEPS = [(0, 100), (5000, 50), (10000, 20)]


@pytest.mark.parametrize(
    "price, expected, floor_applied",
    [
        (1000, "2000", False),
        (4990, "9980", False),
        (5010, "10000", True),  # без планки было бы 7 515 — дешевле, чем товар за 4 990
        (6000, "10000", True),
        (8000, "12000", False),
        (10010, "15000", True),
        (12000, "15000", True),
        (20000, "24000", False),
        (50000, "60000", False),
    ],
)
def test_price_follows_step_but_never_drops_below_previous_step(price, expected, floor_applied):
    result = apply_scale(STEPS, price)

    assert result.price_with_markup == Decimal(expected)
    assert result.floor_applied is floor_applied


def test_result_explains_which_step_worked():
    result = apply_scale(STEPS, 6000)

    assert (result.step_from, result.step_percent) == (Decimal("5000"), Decimal("50"))
    # 10 000 за товар в 6 000 лир — итоговый процент выше записанного в ступени
    assert result.percent.quantize(Decimal("0.01")) == Decimal("66.67")
    assert apply_scale(STEPS, 8000).percent == Decimal("50")


def test_dearer_source_price_is_never_cheaper_for_customer():
    previous = Decimal("0")
    for price in range(10, 30000, 10):
        current = apply_scale(STEPS, price).price_with_markup
        assert current >= previous, price
        previous = current


def test_floor_accumulates_over_several_steps():
    # вторая ступень короткая: планка третьей ступени не должна «забыть» первую
    steps = [(0, 100), (1000, 10), (1100, 5)]

    assert apply_scale(steps, 1200).price_with_markup == Decimal("2000")


def test_growing_percent_needs_no_floor():
    result = apply_scale([(0, 10), (1000, 30)], 1000)

    assert result.price_with_markup == Decimal("1300")
    assert result.floor_applied is False


def test_steps_order_and_types_do_not_matter():
    shuffled = [("10000", "20"), (Decimal("0"), Decimal("100")), (5000.0, 50)]

    assert apply_scale(shuffled, "5010").price_with_markup == Decimal("10000")


def test_price_below_first_step_uses_first_step():
    assert apply_scale([(100, 40)], 50).price_with_markup == Decimal("70")


@pytest.mark.parametrize("steps, price", [([], 100), (STEPS, None), (STEPS, 0), (STEPS, -5)])
def test_no_scale_or_no_price_gives_nothing(steps, price):
    assert apply_scale(steps, price) is None


def test_examples_cover_both_sides_of_every_threshold():
    assert scale_examples(STEPS) == [
        Decimal("2500"), Decimal("4990"), Decimal("5010"), Decimal("7500"),
        Decimal("9990"), Decimal("10010"), Decimal("20000"),
    ]
    assert scale_examples([(0, 30)]) == [Decimal("1000")]
    assert scale_examples([]) == []


# --- раздел «Шкалы наценки» в админке ---


@pytest.fixture
def admin_client(client, django_user_model, settings):
    # страницы админки ссылаются на статику; в тестах манифеста collectstatic нет
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    client.force_login(
        django_user_model.objects.create_superuser("scale-admin", "scale-admin@example.com", "x" * 20)
    )
    return client


def _scale_form(name, steps):
    data = {
        "name": name,
        "steps-TOTAL_FORMS": str(len(steps)),
        "steps-INITIAL_FORMS": "0",
        "steps-MIN_NUM_FORMS": "0",
        "steps-MAX_NUM_FORMS": "1000",
    }
    for index, (price_from, percent) in enumerate(steps):
        data[f"steps-{index}-price_from"] = str(price_from)
        data[f"steps-{index}-percent"] = str(percent)
    return data


@pytest.mark.django_db
def test_admin_saves_scale_and_shows_examples(admin_client):
    response = admin_client.post(
        reverse("admin:catalog_markupscale_add"), _scale_form("Общая", STEPS)
    )

    assert response.status_code == 302
    scale = MarkupScale.objects.get(name="Общая")
    assert scale.step_pairs() == [
        (Decimal("0"), Decimal("100")),
        (Decimal("5000"), Decimal("50")),
        (Decimal("10000"), Decimal("20")),
    ]

    page = admin_client.get(reverse("admin:catalog_markupscale_change", args=[scale.pk]))
    html = page.content.decode()
    # 5 010 лир → 10 000, а не 7 515
    assert "<td>5 010</td><td>10 000</td><td>99.6</td><td>не дешевле предыдущей ступени</td>" in html
    assert "<td>7 500</td><td>11 250</td><td>50</td><td>ступень 50 %</td>" in html
    # колонка «До» берётся из следующей ступени
    assert "и выше" in html

    listing = admin_client.get(reverse("admin:catalog_markupscale_changelist")).content.decode()
    assert "от 0 — 100 %; от 5 000 — 50 %; от 10 000 — 20 %" in listing


@pytest.mark.django_db
@pytest.mark.parametrize(
    "steps, message",
    [
        ([], "Добавьте хотя бы одну ступень."),
        ([(100, 50)], "Первая ступень должна начинаться с 0 лир."),
    ],
)
def test_admin_rejects_scale_with_gaps(admin_client, steps, message):
    response = admin_client.post(
        reverse("admin:catalog_markupscale_add"), _scale_form("Плохая", steps)
    )

    assert response.status_code == 200
    assert message in response.content.decode()
    assert not MarkupScale.objects.exists()


@pytest.mark.django_db
def test_percent_is_limited_to_500(admin_client):
    response = admin_client.post(
        reverse("admin:catalog_markupscale_add"), _scale_form("Слишком", [(0, 501)])
    )

    assert response.status_code == 200
    assert not MarkupScaleStep.objects.exists()
