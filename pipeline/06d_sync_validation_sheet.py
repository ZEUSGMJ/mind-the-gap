#!/usr/bin/env python3
"""
pipeline/06d_sync_validation_sheet.py

Sync completed human labels from validation_sheet.xlsx back into
validation_sheet.csv so the agreement script can read them.

This script intentionally uses only the Python standard library because the
project environment does not guarantee an XLSX reader dependency.

Run:
    python3 pipeline/06d_sync_validation_sheet.py
"""

from __future__ import annotations

import csv
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / "data" / "results"
CSV_PATH = RESULTS_DIR / "validation_sheet.csv"
XLSX_PATH = RESULTS_DIR / "validation_sheet.xlsx"

NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
SYNC_COLUMNS = ["jisnu_label", "suvarna_label", "jisnu_notes", "suvarna_notes"]


def column_letters(cell_ref: str) -> str:
    """Return the column letters from an Excel cell reference."""
    letters = []
    for char in cell_ref:
        if char.isalpha():
            letters.append(char)
        else:
            break
    return "".join(letters)


def load_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    """Load the shared string table, if present."""
    path = "xl/sharedStrings.xml"
    if path not in archive.namelist():
        return []

    root = ET.fromstring(archive.read(path))
    strings = []
    for item in root.findall("a:si", NS):
        text = "".join(node.text or "" for node in item.iterfind(".//a:t", NS))
        strings.append(text)
    return strings


def cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    """Decode a worksheet cell into plain text."""
    cell_type = cell.attrib.get("t")
    value = cell.find("a:v", NS)
    inline = cell.find("a:is", NS)

    if cell_type == "s" and value is not None:
        return shared_strings[int(value.text)]
    if inline is not None:
        return "".join(node.text or "" for node in inline.iterfind(".//a:t", NS))
    if value is not None and value.text is not None:
        return value.text
    return ""


def normalize_row_num(raw: str) -> str:
    """Normalize workbook row ids like '1.0' to the CSV form '1'."""
    value = (raw or "").strip()
    if value.endswith(".0"):
        value = value[:-2]
    return value


def load_workbook_rows(path: Path) -> list[dict[str, str]]:
    """Read the first worksheet of the validation workbook."""
    with zipfile.ZipFile(path) as archive:
        shared_strings = load_shared_strings(archive)
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))

    rows = []
    header_by_col: dict[str, str] = {}
    for row in root.findall(".//a:sheetData/a:row", NS):
        values_by_col: dict[str, str] = {}
        for cell in row.findall("a:c", NS):
            col = column_letters(cell.attrib.get("r", ""))
            values_by_col[col] = cell_value(cell, shared_strings)

        if not header_by_col:
            header_by_col = {
                col: value.strip() for col, value in values_by_col.items() if value.strip()
            }
            continue

        record = {header: values_by_col.get(col, "") for col, header in header_by_col.items()}
        if any(record.values()):
            rows.append(record)
    return rows


def load_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def main() -> int:
    if not CSV_PATH.exists():
        print(f"Not found: {CSV_PATH}")
        return 1
    if not XLSX_PATH.exists():
        print(f"Not found: {XLSX_PATH}")
        return 1

    workbook_rows = load_workbook_rows(XLSX_PATH)
    fieldnames, csv_rows = load_csv_rows(CSV_PATH)
    csv_by_row = {normalize_row_num(row.get("row_num", "")): row for row in csv_rows}

    updated_rows = 0
    changed_cells = 0

    for workbook_row in workbook_rows:
        row_num = normalize_row_num(workbook_row.get("row_num", ""))
        csv_row = csv_by_row.get(row_num)
        if csv_row is None:
            print(f"Warning: workbook row_num {row_num!r} not found in CSV, skipping")
            continue

        row_changed = False
        for column in SYNC_COLUMNS:
            if column not in fieldnames:
                continue
            new_value = (workbook_row.get(column, "") or "").strip()
            if csv_row.get(column, "") != new_value:
                csv_row[column] = new_value
                changed_cells += 1
                row_changed = True
        if row_changed:
            updated_rows += 1

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"Synced workbook labels into {CSV_PATH}")
    print(f"  Rows updated: {updated_rows}")
    print(f"  Cells changed: {changed_cells}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
