"""Справочные списки для проверки лекарства (TD-044, docs/DRUG_CHECK.md).

Строки — копия открытого файла источника (SKRS E-Reçete TİTCK, прайс склада), загружаемого
раз в неделю. Каталог эти таблицы не меняют: проверка только показывает расхождения.
"""

from django.db import models


class DrugReferenceEntry(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активен"
        PASSIVE = "passive", "Пассивен"
        LISTED = "listed", "Есть в прайсе"
        NOT_PRODUCED = "not_produced", "Не производится"

    source = models.CharField("Источник", max_length=20)
    barcode = models.CharField("Штрихкод", max_length=20)
    name = models.CharField("Название в источнике", max_length=300)
    firm = models.CharField("Фирма", max_length=200, blank=True)
    atc_code = models.CharField("Код АТХ", max_length=20, blank=True)
    status = models.CharField("Статус", max_length=20, choices=Status.choices)
    status_date = models.DateField("Дата статуса", null=True, blank=True)
    reason = models.CharField("Причина / пояснение", max_length=500, blank=True)
    price = models.DecimalField("Цена, TL", max_digits=12, decimal_places=2, null=True, blank=True)
    price_date = models.DateField("Дата цены", null=True, blank=True)
    file_date = models.DateField("Дата файла", null=True, blank=True)

    class Meta:
        verbose_name = "Строка справочного списка"
        verbose_name_plural = "Справочные списки (SKRS, склад)"
        constraints = [
            models.UniqueConstraint(fields=["source", "barcode"], name="drug_reference_source_barcode"),
        ]

    def __str__(self):
        return f"{self.source}: {self.barcode} {self.name}"

    @property
    def source_title(self) -> str:
        from .sources import get_source

        source = get_source(self.source)
        return source.title if source else self.source


class DrugReferenceLoad(models.Model):
    class Result(models.TextChoices):
        LOADED = "loaded", "Загружен"
        UNCHANGED = "unchanged", "Тот же файл"
        FAILED = "failed", "Ошибка"

    source = models.CharField("Источник", max_length=20)
    file_name = models.CharField("Файл", max_length=300, blank=True)
    file_url = models.URLField("Адрес файла", max_length=1000, blank=True)
    file_date = models.DateField("Дата файла", null=True, blank=True)
    result = models.CharField("Итог", max_length=20, choices=Result.choices)
    rows = models.PositiveIntegerField("Строк", default=0)
    message = models.TextField("Сообщение", blank=True)
    created_at = models.DateTimeField("Когда", auto_now_add=True)

    class Meta:
        verbose_name = "Загрузка справочного файла"
        verbose_name_plural = "Загрузки справочных файлов"
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"{self.source} {self.file_name} ({self.get_result_display()})"
