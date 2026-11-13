"""Чтение листов .xlsx без сторонних библиотек.

Справочные файлы (SKRS TİTCK, прайс склада) — обычные книги Excel: ячейки — числа или
общие строки. Своё чтение на zipfile + ElementTree вместо новой зависимости в образе.
Значения отдаются строками как есть (числа — текстом из файла), даты — см. ``excel_date``.
"""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
from datetime import date, datetime, timedelta
from typing import Iterator
from xml.etree import ElementTree

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
EXCEL_EPOCH = date(1899, 12, 30)


class XlsxError(ValueError):
    """Файл не похож на книгу Excel или в нём нет нужного листа."""


def _column_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref or "")
    if not letters:
        return -1
    index = 0
    for char in letters.group(0):
        index = index * 26 + (ord(char) - 64)
    return index - 1


def _text(node) -> str:
    return "".join(t.text or "" for t in node.iter(f"{NS}t"))


class Workbook:
    def __init__(self, content: bytes):
        try:
            self._zip = zipfile.ZipFile(io.BytesIO(content))
            workbook = ElementTree.fromstring(self._zip.read("xl/workbook.xml"))
            rels = ElementTree.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
            raise XlsxError("файл не является книгой Excel (.xlsx)") from exc
        targets = {rel.get("Id"): rel.get("Target", "") for rel in rels.iter(f"{PKG_REL_NS}Relationship")}
        self.sheets: dict[str, str] = {}
        for sheet in workbook.iter(f"{NS}sheet"):
            target = targets.get(sheet.get(f"{REL_NS}id"), "")
            path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
            self.sheets[sheet.get("name", "")] = path
        self._shared: list[str] | None = None

    @property
    def shared_strings(self) -> list[str]:
        if self._shared is None:
            try:
                root = ElementTree.fromstring(self._zip.read("xl/sharedStrings.xml"))
            except KeyError:
                root = None
            self._shared = [_text(item) for item in root.iter(f"{NS}si")] if root is not None else []
        return self._shared

    def rows(self, sheet_name: str) -> Iterator[list[str | None]]:
        """Строки листа списками значений; пустые ячейки — None."""
        path = self.sheets.get(sheet_name)
        if path is None:
            raise XlsxError(f"в файле нет листа «{sheet_name}»")
        shared = self.shared_strings
        with self._zip.open(path) as stream:
            for _event, row in ElementTree.iterparse(stream):
                if row.tag != f"{NS}row":
                    continue
                values: list[str | None] = []
                for cell in row.iter(f"{NS}c"):
                    index = _column_index(cell.get("r", ""))
                    if index < 0:
                        index = len(values)
                    kind = cell.get("t")
                    value_node = cell.find(f"{NS}v")
                    raw = value_node.text if value_node is not None else None
                    if kind == "s" and raw is not None:
                        value = shared[int(raw)]
                    elif kind == "inlineStr":
                        inline = cell.find(f"{NS}is")
                        value = _text(inline) if inline is not None else None
                    else:
                        value = raw
                    while len(values) < index:
                        values.append(None)
                    values.append(value)
                row.clear()
                yield values


def cell(row: list, index: int) -> str:
    """Значение ячейки без пробелов по краям, пустая строка вместо None."""
    if index >= len(row) or row[index] is None:
        return ""
    return str(row[index]).strip()


def excel_date(value) -> date | None:
    """Дата из ячейки: серийный номер Excel (46336) или текст «10.11.2026»."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        serial = float(text)
    except ValueError:
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(text[:10], fmt).date()
            except ValueError:
                continue
        return None
    if not 1 < serial < 2958465:
        return None
    return EXCEL_EPOCH + timedelta(days=int(serial))


def barcode_from(value) -> str:
    """Штрихкод из ячейки: число в файле бывает «8699809156982» или «8.699809156982E12»."""
    text = str(value or "").strip()
    if re.fullmatch(r"\d+(\.0+)?", text):
        return text.split(".")[0]
    if re.fullmatch(r"\d(\.\d+)?[eE]\+?\d+", text):
        return str(int(float(text)))
    return ""
