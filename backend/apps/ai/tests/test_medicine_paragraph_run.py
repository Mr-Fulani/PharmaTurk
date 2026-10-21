"""AI-прогон «Перевод абзацев инструкций (Batch API)»: оценка, части, стоп, повтор, админка."""

import json
from types import SimpleNamespace

import pytest
from django.urls import reverse

from apps.ai.models import AIRun, AITranslationMemory
from apps.ai.services import ai_runs
from apps.ai.services.medicine_memory import PARAGRAPH_NAMESPACE
from apps.ai.services.translation_memory import remember
from apps.ai.tests.test_medicine_code_pipeline import (
    _fake_batch_client,
    _numbered,
    _part_products,
    _skip_fourth,
    _translate_numbered,
)
from apps.ai.tasks import advance_medicine_paragraph_run

pytestmark = pytest.mark.django_db


@pytest.fixture
def celery(monkeypatch):
    """Перехват постановки задач: ничего не уходит в брокер."""
    calls = SimpleNamespace(ticks=[], previews=[])
    monkeypatch.setattr(
        "apps.ai.tasks.advance_medicine_paragraph_run.apply_async",
        lambda args, **kw: calls.ticks.append((args, kw["countdown"])),
    )
    monkeypatch.setattr(
        "apps.ai.tasks.preview_medicine_paragraph_run.apply_async", lambda args, **kw: calls.previews.append(args)
    )
    return calls


@pytest.fixture
def openai(monkeypatch):
    """Фейковый Batch API: пакет готов сразу; ``skip`` — модель пропускает 4-й абзац в запросе из 10."""
    state = SimpleNamespace(skip=False, uploaded={})

    def answer(items):
        if state.skip and len(items) == 10:
            return _skip_fourth(items)
        return {key: dict(zip(("ru", "en"), _translate_numbered(text))) for key, text in items.items()}

    monkeypatch.setattr(ai_runs, "LLMClient", _fake_batch_client(state.uploaded, _translate_numbered, answer))
    state.batches = state.uploaded.setdefault("batches", [])
    return state


@pytest.fixture
def plain_static(settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_superuser("paragraphs", "paragraphs@example.com", "x")


def _create(user, capture, part_size=10, max_defect=0.15, wait_each_part=False):
    with capture(execute=True):
        run = ai_runs.create_paragraph_preview(
            user=user, part_size=part_size, max_defect=max_defect, wait_each_part=wait_each_part
        )
    assert ai_runs.preview_paragraph_run(run.pk) == "previewed"
    run.refresh_from_db()
    return run


def _do(action, run, capture):
    with capture(execute=True):
        action(run)
    run.refresh_from_db()
    return run


def _tick(run, capture):
    run.refresh_from_db()
    with capture(execute=True):
        result = ai_runs.advance_paragraph_run(run.pk, run.tick_token)
    run.refresh_from_db()
    return result


def _sent(state, file_id):
    return [
        text for line in state.uploaded["files"][file_id].splitlines()
        for text in json.loads(json.loads(line)["body"]["messages"][1]["content"].split("\n\n", 1)[1]).values()
    ]


def test_preview_counts_missing_paragraphs_parts_and_cost(celery, user, django_capture_on_commit_callbacks):
    _part_products(4)
    remember(PARAGRAPH_NAMESPACE, {_numbered(2)[0]: {"ru": "есть", "en": "cached"}})

    run = _create(user, django_capture_on_commit_callbacks)

    preview = run.report["preview"]
    assert celery.previews == [[run.pk]]
    assert run.status == AIRun.Status.DRAFT and run.selected_count == 23
    # 11 абзацев набрано на втором лекарстве, третье и четвёртое — вторая часть.
    assert preview["parts"] == 2 and preview["requests"] == 4
    assert preview["cost_usd"] > 0 and preview["regular_cost_usd"] == pytest.approx(preview["cost_usd"] * 2)
    assert "Не в памяти переводов 23 абзацев" in preview["summary"] and "2 частей" in preview["summary"]
    assert float(run.estimated_cost_usd) == pytest.approx(preview["cost_usd"], abs=1e-4)


def test_run_sends_parts_one_by_one_collects_and_finishes(
    celery, openai, user, django_capture_on_commit_callbacks
):
    pks = _part_products(4)
    run = _do(ai_runs.start_paragraph_run, _create(user, django_capture_on_commit_callbacks),
              django_capture_on_commit_callbacks)
    assert run.status == AIRun.Status.RUNNING and celery.ticks[-1][1] == 0

    assert _tick(run, django_capture_on_commit_callbacks) == "submitted"
    first = openai.batches[0]
    assert first.metadata == {
        "kind": PARAGRAPH_NAMESPACE, "part": "1", "paragraphs": "12", "last_product": str(pks[1]),
        "retry_of": "", "run": str(run.pk),
    }
    assert celery.ticks[-1][1] == ai_runs.PARAGRAPH_TICK_SECONDS

    first.status = "in_progress"
    assert _tick(run, django_capture_on_commit_callbacks) == "waiting"
    assert run.report["parts"][0]["state"] == "in_progress" and len(openai.batches) == 1

    first.status = "completed"
    assert _tick(run, django_capture_on_commit_callbacks) == "submitted"
    part = run.report["parts"][0]
    assert part["state"] == "collected" and part["accepted"] == 12 and part["defect_count"] == 0
    assert part["cost_usd"] == pytest.approx(0.00075)  # 2 запроса × (1000 × $0.15 + 1000 × $0.60) / 1 млн / 2
    second = openai.batches[1]
    assert second.metadata["part"] == "2" and second.metadata["last_product"] == str(pks[3])
    assert _numbered(14)[0] in _sent(openai, "file-in-2") and _numbered(13)[0] not in _sent(openai, "file-in-2")

    assert _tick(run, django_capture_on_commit_callbacks) == "finished"
    assert run.status == AIRun.Status.FINISHED and "Проход по каталогу закончен" in run.message
    assert (run.queued_count, run.done_count, run.failed_count) == (24, 24, 0)
    assert float(run.cost_usd) == pytest.approx(0.0015)
    assert AITranslationMemory.objects.filter(namespace=PARAGRAPH_NAMESPACE).count() == 24
    state = ai_runs.paragraph_state(run)
    assert state["percent"] == 100 and state["per_1000"] == "0.0625"
    assert not (state["can_next"] or state["can_retry"] or state["can_stop"] or state["can_resume"])


def test_high_defect_stops_run_and_retry_sends_only_rejected(
    celery, openai, user, django_capture_on_commit_callbacks
):
    pks = _part_products(3)
    openai.skip = True
    run = _do(ai_runs.start_paragraph_run, _create(user, django_capture_on_commit_callbacks),
              django_capture_on_commit_callbacks)
    _tick(run, django_capture_on_commit_callbacks)

    assert _tick(run, django_capture_on_commit_callbacks) == "stopped"
    assert run.status == AIRun.Status.STOPPED and len(openai.batches) == 1
    assert "брак выше порога" in run.message and "брак 10 (83.3%, порог 15%)" in run.message
    assert "сдвиг ответа 10" in run.message
    assert run.report["parts"][0]["shifted_requests"] == 1
    state = ai_runs.paragraph_state(run)
    assert state["can_retry"] and state["can_next"] and state["retry_count"] == 10

    openai.skip = False
    run = _do(ai_runs.retry_paragraph_part, run, django_capture_on_commit_callbacks)
    assert run.status == AIRun.Status.RUNNING
    assert _tick(run, django_capture_on_commit_callbacks) == "submitted"
    retry = openai.batches[1]
    assert retry.metadata["retry_of"] == "batch-1" and retry.metadata["paragraphs"] == "10"
    assert _sent(openai, "file-in-2") == [_numbered(i)[0] for i in range(2, 12)]
    assert run.report["parts"][1]["retry_of"] == 1

    # Повтор принят — дальше следующая часть каталога, с лекарства после первой части.
    assert _tick(run, django_capture_on_commit_callbacks) == "submitted"
    third = openai.batches[2]
    assert third.metadata["part"] == "3" and third.metadata["last_product"] == str(pks[2])
    assert _tick(run, django_capture_on_commit_callbacks) == "finished"
    assert (run.done_count, run.failed_count) == (18, 0)
    assert AITranslationMemory.objects.filter(namespace=PARAGRAPH_NAMESPACE).count() == 18


def test_stop_waits_for_part_in_openai_then_next_part_continues(
    celery, openai, user, django_capture_on_commit_callbacks
):
    pks = _part_products(4)
    run = _do(ai_runs.start_paragraph_run, _create(user, django_capture_on_commit_callbacks),
              django_capture_on_commit_callbacks)
    _tick(run, django_capture_on_commit_callbacks)
    openai.batches[0].status = "in_progress"

    run = _do(ai_runs.stop_paragraph_run, run, django_capture_on_commit_callbacks)
    assert run.status == AIRun.Status.RUNNING and run.report["stop_requested"]
    assert "Часть №1 уже в OpenAI" in run.message
    assert not ai_runs.paragraph_state(run)["can_stop"]
    with pytest.raises(ai_runs.RunError, match="уже запрошена"):
        ai_runs.stop_paragraph_run(run)
    assert _tick(run, django_capture_on_commit_callbacks) == "waiting"

    openai.batches[0].status = "completed"
    assert _tick(run, django_capture_on_commit_callbacks) == "stopped"
    assert run.status == AIRun.Status.STOPPED and run.message.startswith("Остановлен вручную. Часть №1")
    assert len(openai.batches) == 1 and "stop_requested" not in run.report
    assert ai_runs.paragraph_state(run)["can_next"]

    run = _do(ai_runs.next_paragraph_part, run, django_capture_on_commit_callbacks)
    assert _tick(run, django_capture_on_commit_callbacks) == "submitted"
    assert openai.batches[1].metadata["last_product"] == str(pks[3])

    _tick(run, django_capture_on_commit_callbacks)
    assert run.status == AIRun.Status.FINISHED


def test_stop_before_first_part_is_immediate(celery, openai, user, django_capture_on_commit_callbacks):
    _part_products(2)
    run = _do(ai_runs.start_paragraph_run, _create(user, django_capture_on_commit_callbacks),
              django_capture_on_commit_callbacks)
    token = run.tick_token

    run = _do(ai_runs.stop_paragraph_run, run, django_capture_on_commit_callbacks)

    assert run.status == AIRun.Status.STOPPED and "Следующая часть" in run.message
    assert ai_runs.advance_paragraph_run(run.pk, token) == "skipped"
    assert not openai.batches


def test_wait_each_part_pauses_after_every_part(celery, openai, user, django_capture_on_commit_callbacks):
    _part_products(4)
    run = _create(user, django_capture_on_commit_callbacks, wait_each_part=True)
    run = _do(ai_runs.start_paragraph_run, run, django_capture_on_commit_callbacks)
    _tick(run, django_capture_on_commit_callbacks)

    assert _tick(run, django_capture_on_commit_callbacks) == "stopped"
    assert run.status == AIRun.Status.STOPPED and "нажмите «Следующая часть»" in run.message
    assert "брак 0 (0.0%, порог 15%)" in run.message and len(openai.batches) == 1


def test_part_is_not_sent_while_other_part_runs_in_openai(
    celery, openai, user, django_capture_on_commit_callbacks
):
    _part_products(2)
    openai.batches.append(SimpleNamespace(
        id="batch-console", status="in_progress", metadata={"kind": PARAGRAPH_NAMESPACE, "part": "7"}
    ))
    run = _do(ai_runs.start_paragraph_run, _create(user, django_capture_on_commit_callbacks),
              django_capture_on_commit_callbacks)

    assert _tick(run, django_capture_on_commit_callbacks) == "busy"
    assert run.status == AIRun.Status.STOPPED and "№7 batch-console (in_progress)" in run.message
    assert len(openai.batches) == 1


def test_failed_part_is_resent_by_next_part(celery, openai, user, django_capture_on_commit_callbacks):
    pks = _part_products(2)
    run = _do(ai_runs.start_paragraph_run, _create(user, django_capture_on_commit_callbacks),
              django_capture_on_commit_callbacks)
    _tick(run, django_capture_on_commit_callbacks)
    openai.batches[0].status = "failed"
    openai.batches[0].output_file_id = None

    assert _tick(run, django_capture_on_commit_callbacks) == "part_failed"
    assert run.status == AIRun.Status.STOPPED and "OpenAI не вернул ни одного перевода части №1" in run.message
    assert run.report["parts"][0]["state"] == "failed" and run.queued_count == 0

    run = _do(ai_runs.next_paragraph_part, run, django_capture_on_commit_callbacks)
    _tick(run, django_capture_on_commit_callbacks)
    assert openai.batches[1].metadata["last_product"] == str(pks[1])
    assert _sent(openai, "file-in-2") == _sent(openai, "file-in-1")


def test_step_failure_can_be_resumed_and_second_run_is_refused(
    celery, openai, user, django_capture_on_commit_callbacks, monkeypatch
):
    _part_products(2)
    run = _do(ai_runs.start_paragraph_run, _create(user, django_capture_on_commit_callbacks),
              django_capture_on_commit_callbacks)
    other = _create(user, django_capture_on_commit_callbacks)
    with pytest.raises(ai_runs.RunError, match="Уже идёт другой перевод абзацев"):
        ai_runs.start_paragraph_run(other)

    running_parts = ai_runs.batch_api.running_parts
    monkeypatch.setattr(ai_runs.batch_api, "running_parts", lambda client: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        advance_medicine_paragraph_run(run.pk, run.tick_token)
    run.refresh_from_db()
    assert run.status == AIRun.Status.FAILED and "Можно нажать «Продолжить»" in run.message
    assert ai_runs.paragraph_state(run)["can_resume"]

    monkeypatch.setattr(ai_runs.batch_api, "running_parts", running_parts)
    run = _do(ai_runs.resume_run, run, django_capture_on_commit_callbacks)
    assert run.status == AIRun.Status.RUNNING
    assert _tick(run, django_capture_on_commit_callbacks) == "submitted"


def test_admin_paragraph_page_count_start_stop(
    client, celery, openai, user, plain_static, django_capture_on_commit_callbacks
):
    _part_products(2)
    client.force_login(user)
    assert "Перевести абзацы инструкций" in client.get(reverse("admin:ai_airun_changelist")).content.decode()
    form_url = reverse("admin:ai_airun_paragraphs")
    assert "Посчитать" in client.get(form_url).content.decode()

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(form_url, {"part_size": "10", "max_defect": "15"})
    run = AIRun.objects.get(kind=AIRun.Kind.MEDICINE_PARAGRAPHS)
    assert response.status_code == 302 and run.report["settings"] == {
        "part_size": 10, "max_defect": 0.15, "wait_each_part": False,
    }
    page_url = reverse("admin:ai_airun_change", args=[run.pk])
    assert "Считаем" in client.get(page_url).content.decode()
    ai_runs.preview_paragraph_run(run.pk)
    page = client.get(page_url).content.decode()
    assert "Не в памяти переводов 12 абзацев" in page and "▶ Запустить" in page

    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("admin:ai_airun_confirm", args=[run.pk]))
    run.refresh_from_db()
    assert run.status == AIRun.Status.RUNNING
    _tick(run, django_capture_on_commit_callbacks)
    openai.batches[0].status = "in_progress"
    _tick(run, django_capture_on_commit_callbacks)

    page = client.get(page_url).content.decode()
    assert "batch-1" in page and "переводится в OpenAI" in page and "■ Стоп" in page
    status = client.get(reverse("admin:ai_airun_status", args=[run.pk])).json()
    assert status["parts_key"] == "1:in_progress:0" and status["can_stop"] and status["in_flight"]
    assert client.get(reverse("admin:ai_airun_delete", args=[run.pk])).status_code == 403

    client.post(reverse("admin:ai_airun_stop", args=[run.pk]))
    run.refresh_from_db()
    assert run.report["stop_requested"] and "Остановка" in client.get(page_url).content.decode()
    response = client.post(reverse("admin:ai_airun_next_part", args=[run.pk]), follow=True)
    assert "Следующую часть можно отправить" in response.content.decode()
