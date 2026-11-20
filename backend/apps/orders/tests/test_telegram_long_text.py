"""Длинный текст заявки: Telegram режет подпись и сообщение, менеджер не теряет ни того ни другого."""

import re
from collections import Counter
from html import unescape
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.orders.tasks import (
    TELEGRAM_CAPTION_LIMIT,
    TELEGRAM_MAX_MESSAGE_PARTS,
    TELEGRAM_MESSAGE_LIMIT,
    _split_tg_text,
    _tg_html_escape,
    _tg_length,
    _tg_link,
    notify_new_order_telegram,
    notify_sourcing_request_telegram,
)
from apps.orders.tests.test_request_telegram_notification import _order

ADMIN = "admin-chat"
CUSTOMER = "555"
PDF = b"%PDF-1.4 receipt"


TAG_RE = re.compile(r"<(/?)(b|code|a)( href=\"[^\"<>]*\")?>")


def _visible_length(text):
    """Длина после разбора HTML: так считает Telegram — без тегов, «&amp;» за один знак."""
    return _tg_length(unescape(TAG_RE.sub("", text)))


def _assert_valid_html(case, text):
    """Правила разбора Telegram: «&» только в &amp; &lt; &gt; &quot;, «<» и «>» только в тегах, теги закрыты."""
    plain = re.sub(r"&(amp|lt|gt|quot);", "", text)
    case.assertNotIn("&", plain, f"Оборванная сущность: {text[:40]!r} … {text[-40:]!r}")
    case.assertNotRegex(TAG_RE.sub("", plain), "[<>]", f"Оборванный тег: {text[:60]!r} … {text[-60:]!r}")
    open_tag = ""
    for closing, name, _href in TAG_RE.findall(plain):
        if closing:
            case.assertEqual(open_tag, name, f"Лишний закрывающий тег: {text[:60]!r}")
            open_tag = ""
        else:
            case.assertEqual(open_tag, "", "Вложенные теги шаблон не использует")
            open_tag = name
    case.assertEqual(open_tag, "", f"Незакрытый тег: {text[-60:]!r}")


class FakeTelegram:
    """Отвечает как Bot API: 400 на длинный текст и сломанную разметку, по чату можно задать сбои."""

    def __init__(self, post, failures=None):
        self.calls = []
        self.failures = failures or {}
        post.side_effect = self.reply

    def reply(self, url, **kwargs):
        method = url.rsplit("/", 1)[-1]
        payload = kwargs.get("json") or kwargs.get("data")
        call = SimpleNamespace(
            method=method,
            chat_id=payload["chat_id"],
            text=payload.get("text") or payload.get("caption") or "",
        )
        self.calls.append(call)
        failure = self.failures.get(len(self.calls))
        if failure:
            return SimpleNamespace(status_code=failure, ok=False)
        limit = TELEGRAM_MESSAGE_LIMIT if method == "sendMessage" else TELEGRAM_CAPTION_LIMIT
        if _visible_length(call.text) > limit:
            return SimpleNamespace(status_code=400, ok=False)
        return SimpleNamespace(status_code=200, ok=True)

    def delivered(self, chat_id=ADMIN):
        return [call for call in self.calls if call.chat_id == chat_id]


@override_settings(TELEGRAM_BOT_TOKEN="test-token", TELEGRAM_CHAT_ID=ADMIN)
@patch("apps.orders.tasks.generate_and_save_receipt", return_value=("", None))
@patch("apps.orders.tasks._load_receipt_pdf_from_storage", return_value=PDF)
@patch("apps.orders.tasks.requests.post")
@patch("apps.orders.models.Order.objects.select_related")
class LongOrderTextTests(SimpleTestCase):
    def _run(self, select_related, comment):
        select_related.return_value.get.return_value = _order(comment=comment)
        return notify_new_order_telegram.apply(kwargs={"order_id": 9})

    def test_short_comment_stays_in_the_caption(self, select_related, post, *_):
        telegram = FakeTelegram(post)

        self._run(select_related, "Позвоните вечером")

        calls = telegram.delivered()
        self.assertEqual([call.method for call in calls], ["sendDocument"])
        self.assertIn("Позвоните вечером", calls[0].text)

    def test_comment_over_caption_limit_reaches_manager_with_receipt(self, select_related, post, *_):
        telegram = FakeTelegram(post)
        comment = "Очень подробный комментарий. " * 40

        self._run(select_related, comment)

        calls = telegram.delivered()
        self.assertEqual([call.method for call in calls], ["sendMessage", "sendDocument"])
        self.assertIn(comment.strip(), calls[0].text)
        self.assertIn("+79990000000", calls[0].text)
        self.assertIn("REQ-9", calls[1].text)
        self.assertLessEqual(_tg_length(calls[1].text), TELEGRAM_CAPTION_LIMIT)

    def test_comment_over_message_limit_is_delivered_in_parts(self, select_related, post, *_):
        telegram = FakeTelegram(post)
        words = [f"слово{index}" for index in range(1500)]

        self._run(select_related, " ".join(words))

        calls = telegram.delivered()
        self.assertEqual(calls[-1].method, "sendDocument")
        texts = [call.text for call in calls[:-1]]
        self.assertGreater(len(texts), 1)
        for text in texts:
            self.assertLessEqual(_tg_length(text), TELEGRAM_MESSAGE_LIMIT)
        joined = " ".join(texts)
        for word in words:
            self.assertIn(word, joined)

    def test_long_text_without_pdf_is_delivered_in_parts(self, select_related, post, load_pdf, *_):
        load_pdf.return_value = None
        telegram = FakeTelegram(post)

        self._run(select_related, "текст " * 2000)

        calls = telegram.delivered()
        self.assertGreater(len(calls), 1)
        self.assertEqual({call.method for call in calls}, {"sendMessage"})
        for call in calls:
            self.assertLessEqual(_tg_length(call.text), TELEGRAM_MESSAGE_LIMIT)

    def test_customer_gets_one_short_caption_with_long_comment(self, select_related, post, *_):
        telegram = FakeTelegram(post)

        self._run(select_related, "текст " * 2000)

        calls = telegram.delivered(CUSTOMER)
        self.assertEqual([call.method for call in calls], ["sendDocument"])

    def test_failed_receipt_retry_does_not_repeat_delivered_text(self, select_related, post, *_):
        # Текст дошёл (1), чек упал на 503 (2), покупатель (3), на повторе только чек (4)
        telegram = FakeTelegram(post, failures={2: 503})

        self._run(select_related, "Очень подробный комментарий. " * 40)

        self.assertEqual(
            [call.method for call in telegram.delivered()],
            ["sendMessage", "sendDocument", "sendDocument"],
        )
        self.assertEqual(len(telegram.delivered(CUSTOMER)), 1)

    def test_failed_part_retry_resumes_from_that_part(self, select_related, post, *_):
        telegram = FakeTelegram(post, failures={2: 429})

        # Слова разные: одинаковые части комментария не спутать с повтором отправки
        self._run(select_related, " ".join(f"слово{index}" for index in range(1300)))

        calls = telegram.delivered()
        texts = [call.text for call in calls if call.method == "sendMessage"]
        self.assertEqual(texts[1], texts[2])
        self.assertEqual(Counter(texts).most_common(1)[0][1], 2)
        self.assertEqual(len(telegram.delivered(CUSTOMER)), 1)

    def test_escaped_comment_is_valid_html_in_every_part(self, select_related, post, *_):
        telegram = FakeTelegram(post)

        self._run(select_related, 'Тег <b>жирный</i> & "кавычки" &amp; <a href="x"> снэйк_кейс *звёзды* ' * 400)

        calls = telegram.delivered()
        self.assertGreater(len(calls), 2)
        for call in calls:
            _assert_valid_html(self, call.text)


class SplitTextTests(SimpleTestCase):
    def test_short_text_is_not_split(self):
        self.assertEqual(_split_tg_text("короткий текст"), ["короткий текст"])

    def test_parts_prefer_line_breaks(self):
        lines = ["строка " + str(index) for index in range(1000)]

        parts = _split_tg_text("\n".join(lines))

        self.assertGreater(len(parts), 1)
        self.assertEqual("\n".join(parts).split("\n"), lines)

    def test_cut_never_lands_inside_an_escaped_char(self):
        for padding in range(5):
            text = "а" * padding + _tg_html_escape("&" * 2000)

            parts = _split_tg_text(text)

            self.assertGreater(len(parts), 1)
            self.assertEqual("".join(parts), text)
            for part in parts:
                _assert_valid_html(self, part)

    def test_cut_never_lands_inside_a_tag_or_a_link(self):
        link = _tg_link("https://example.com/admin/drug_check/lookup/?q=NEXIUM%2040%20MG", "Проверить по источникам")
        for separator in (" ", ""):
            for padding in range(0, 120, 7):
                text = "а" * padding + separator.join([f"<b>Позиция</b> {link}"] * 80)

                parts = _split_tg_text(text)

                self.assertGreater(len(parts), 1)
                self.assertEqual(sum(part.count("</a>") for part in parts), 80)
                for part in parts:
                    self.assertLessEqual(_tg_length(part), TELEGRAM_MESSAGE_LIMIT)
                    _assert_valid_html(self, part)

    def test_emoji_counts_as_two_units(self):
        parts = _split_tg_text("😀" * 3000)

        self.assertEqual(len(parts), 2)
        for part in parts:
            self.assertLessEqual(_tg_length(part), TELEGRAM_MESSAGE_LIMIT)

    def test_blank_parts_are_dropped(self):
        parts = _split_tg_text("начало" + "\n" * 9000 + "конец")

        self.assertEqual(parts, ["начало", "конец"])

    def test_huge_text_is_capped_with_a_notice(self):
        parts = _split_tg_text("слово " * 200_000)

        self.assertEqual(len(parts), TELEGRAM_MAX_MESSAGE_PARTS)
        self.assertLessEqual(_tg_length(parts[-1]), TELEGRAM_MESSAGE_LIMIT)
        self.assertIn("админке", parts[-1])
        self.assertNotIn("админке", parts[0])


@override_settings(TELEGRAM_BOT_TOKEN="test-token", TELEGRAM_CHAT_ID=ADMIN)
@patch("apps.orders.tasks.requests.post")
@patch("apps.orders.models.SourcingRequest.objects.get")
class LongSourcingTextTests(SimpleTestCase):
    def _run(self, get_request, comment):
        get_request.return_value = SimpleNamespace(
            pk=4,
            source_url="https://example.com/item_1",
            comment=comment,
            quantity=1,
            contact_name="Анна",
            contact_phone="+79990001122",
            contact_email="",
            contact_channel="whatsapp",
            contact_username="",
            locale="",
            image=SimpleNamespace(open=lambda mode: BytesIO(b"jpeg-bytes")),
        )
        return notify_sourcing_request_telegram.apply(args=[4])

    def test_short_text_stays_in_the_photo_caption(self, get_request, post):
        telegram = FakeTelegram(post)

        self._run(get_request, "Нужен размер M")

        calls = telegram.delivered()
        self.assertEqual([call.method for call in calls], ["sendPhoto"])
        self.assertIn("Нужен размер M", calls[0].text)

    def test_long_text_goes_in_full_before_the_photo(self, get_request, post):
        telegram = FakeTelegram(post)
        comment = "снэйк_кейс " * 180

        self._run(get_request, comment)

        calls = telegram.delivered()
        self.assertEqual([call.method for call in calls], ["sendMessage", "sendPhoto"])
        self.assertIn(comment.strip(), calls[0].text)
        self.assertIn("+79990001122", calls[0].text)
        for call in calls:
            _assert_valid_html(self, call.text)

    @override_settings(SITE_URL="https://site.test")
    def test_buyer_text_fills_the_drug_lookup_search_field(self, get_request, post):
        telegram = FakeTelegram(post)

        self._run(get_request, "Нужен  NEXIUM 40 mg\n& <аналог>?")

        text = telegram.delivered()[0].text
        self.assertIn(
            '<a href="https://site.test/admin/drug_check/drugreferenceentry/lookup/'
            '?q=%D0%9D%D1%83%D0%B6%D0%B5%D0%BD%20NEXIUM%2040%20mg%20%26%20%3C%D0%B0%D0%BD%D0%B0%D0%BB%D0%BE%D0%B3%3E%3F">'
            "проверить по источникам</a>",
            text,
        )
        self.assertIn("Комментарий: Нужен  NEXIUM 40 mg\n&amp; &lt;аналог&gt;?", text)
        _assert_valid_html(self, text)

    @override_settings(SITE_URL="https://site.test")
    def test_long_buyer_text_is_cut_in_the_lookup_link(self, get_request, post):
        telegram = FakeTelegram(post)

        self._run(get_request, "я" * 500)

        self.assertIn('lookup/?q=' + "%D1%8F" * 100 + '">', telegram.delivered()[0].text)

    @override_settings(SITE_URL="https://site.test")
    def test_request_without_text_links_to_the_empty_lookup(self, get_request, post):
        telegram = FakeTelegram(post)

        self._run(get_request, "")

        self.assertIn('<a href="https://site.test/admin/drug_check/drugreferenceentry/lookup/">', telegram.delivered()[0].text)

    def test_failed_photo_retry_does_not_repeat_delivered_text(self, get_request, post):
        telegram = FakeTelegram(post, failures={2: 503})

        self._run(get_request, "снэйк_кейс " * 180)

        self.assertEqual(
            [call.method for call in telegram.delivered()],
            ["sendMessage", "sendPhoto", "sendPhoto"],
        )
