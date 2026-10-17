#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inventory.py — генерация инвентаризации модулей системы КРАБ.

Читает оригинальные тексты ОС ДИСПАК из каталога original/, декодирует их
и формирует таблицу модулей в Markdown: имя файла, размер, шифр задачи,
внутреннее имя и краткое описание из шапки модуля.

Использование:
    inventory.py original/ -o docs/INVENTORY.md
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode import decode_file  # noqa: E402

# Строки шапки паспорта ОС Диспак, которые не являются описанием модуля.
HEADER_KEYS = (
    "ШИФР", "ИМЯ", "ЛИС", "ЛИСТ", "ВРЕ", "ТРА", "ЛЕНТ", "ЛЕН", "ОЗУ",
    "АЦП", "АЦПУ", "БЛО", "РОС", "ТЕЛ", "ВЫВ", "БЗ", "БЧ", "ПЕЧ", "ПЕР",
    "ЕЕВ", "NАМЕ", "Инв", "$", "ТАРЕ", "ВЕМ", "ВВД", "БИБЛИОТЕЧНЫЙ",
)

# Строка пригодна как описание, если содержит хотя бы два слова из
# русских букв длиной не менее четырёх знаков.
_WORD = re.compile(r"[А-ЯЁа-яё]{4,}")

# Логические группы модулей по назначению.
GROUPS = [
    ("Монитор абонентов и ядро системы", (
        "L1", "L2", "START", "KARI", "KOMP", "KSM", "KONT", "ELTR",
        "KODGK", "KODKG", "PEREK", "TERMIN", "RESUR", "R1", "EKARI",
        "ILAM", "DIMIP",
    )),
    ("Бюджетно-статистическая подсистема (БСС)", (
        "BUD0", "BUD1", "BUD2", "BUD3", "BUD4", "BUD5", "BUD6",
        "JITG", "ZMGT1", "ZMGU0", "ZMGU1", "ZMGU2", "ZMGU3", "ZMGU4",
        "ZMGU5", "ZMGU6", "UPRKEY",
    )),
    ("Подсистема Сервис (архив и библиотеки)", (
        "C1", "C2", "C3", "C4", "CA1", "CA2", "CA3", "CA3D", "CA4",
        "CA40", "CA4D", "CA5", "FNARI", "FNRED", "FNERE", "FNC1",
        "FNC2", "FADM", "ARIN", "TEKC", "KATALF",
    )),
    ("Формирователи задач", (
        "FFOR", "FORPS", "FORPZ", "FPZ", "FDPZ", "FAWPZ", "FBUI",
        "FC", "FOTL", "FPOST", "FPRN", "FWYD", "F10", "F11", "F12",
        "F13", "F14", "F15", "F21", "F22", "F23", "F24", "F25", "F26",
        "BUFER", "TESFOR", "WYZYL", "ZPRWS",
    )),
    ("Программа Лист и вывод", (
        "PK1", "PK2", "PKN", "PMET", "GRAF", "SGRAF", "TB6", "TE1",
        "ZGKT", "ZSETX", "ZPKT", "ZPKT1", "ZPS1", "ZPS2", "ZAMES",
        "TITM", "TRML", "SRDDUB", "RDML", "KOPIQ",
    )),
    ("Школа системы Краб (обучение)", (
        "SCU1", "SCU2", "SCU101", "SCU102", "SCU103", "SCU104", "SCU105",
        "SCU106", "SCU107", "SCU108", "SCU109", "SCU110", "SCU201",
        "SCU202", "SCU203", "SCU301", "SCU302", "SCU401", "SCU402",
        "SCU501", "SCU502", "SCU601", "SCUINF", "nnnn", "nnnnn",
    )),
    ("Служебные программы и сопровождение", (
        "SLZ0", "SLZ1", "SLZ2", "SLZ3", "SLZ4", "SLZ5", "SLZ6", "SLZ7",
        "CBOR1", "CBOR2", "CBOR3", "CBOR4", "CBOR5", "SLK", "SLSI",
        "OSIPM", "PP1", "PP2", "SPROT", "SP200", "SP201", "SPSM",
        "SAP", "SMAGZ", "SKB61", "SKB62", "SDOP", "SCUINF",
    )),
    ("Сеть ЭВМ НЕРПА (драйверы и протоколы)", (
        "DS1E", "DS2", "DS2E", "DS3", "DS3E", "DS3T", "DC1", "DC1T",
        "SNET", "SLETTE",
    )),
    ("Документация и постановка", (
        "TTT", "POST", "SREF", "SOGL", "SLETTE", "SDOP", "SGRAF",
        "SEKDZF", "TRML", "SAP",
    )),
]


def clean_line(line: str) -> str:
    return line.rstrip("^").rstrip()


def is_header(line: str) -> bool:
    stripped = line.strip()
    return any(stripped.startswith(key) for key in HEADER_KEYS)


def extract(pasport_lines: list[str]) -> tuple[str, str, str]:
    """Возвращает (шифр, имя, описание) из шапки модуля."""
    shifr = ""
    ime = ""
    desc = ""

    for line in pasport_lines[:14]:
        if not shifr:
            match = re.match(r"^ШИФР\s+(\S+)", line)
            if match:
                shifr = match.group(1)
        if not ime:
            match = re.match(r"^ИМЯ\s+(\S+)", line)
            if match:
                ime = match.group(1)

    for line in pasport_lines[:70]:
        text = line.strip().strip("*").strip()
        if len(text) < 12:
            continue
        if is_header(text):
            continue
        if len(_WORD.findall(text)) < 2:
            continue
        if re.fullmatch(r"[\s\d\-—()№./:=]*", text):
            continue
        desc = re.sub(r"\s{2,}", " ", text)
        break

    return shifr, ime, desc


def main() -> int:
    parser = argparse.ArgumentParser(description="Инвентаризация модулей КРАБ")
    parser.add_argument("source", help="каталог оригинальных текстов")
    parser.add_argument("-o", "--output", help="выходной Markdown-файл")
    args = parser.parse_args()

    records: dict[str, dict] = {}
    for name in sorted(os.listdir(args.source)):
        path = os.path.join(args.source, name)
        if not os.path.isfile(path):
            continue
        text = decode_file(path)
        lines = [clean_line(l) for l in text.split("\n")]
        shifr, ime, desc = extract(lines)
        records[name] = {
            "size": os.path.getsize(path),
            "shifr": shifr,
            "ime": ime,
            "desc": desc,
        }

    grouped: set[str] = set()
    out: list[str] = []
    out.append("# Инвентаризация модулей системы КРАБ\n")
    out.append(
        f"Всего файлов: **{len(records)}**. "
        "Оригиналы хранятся в каталоге `original/` в 8-разрядной "
        "кодировке ОС ДИСПАК; декодированные копии — в `texts/`.\n"
    )
    out.append(
        "Столбцы: **Файл** — имя в архиве; **Байт** — размер оригинала; "
        "**Шифр** — шифр задачи из паспорта ОС Диспак; **Имя** — внутреннее "
        "имя модуля; **Описание** — первая содержательная строка шапки.\n"
    )

    out.append("\n## Состав по подсистемам\n")
    out.append("| Подсистема | Модули |")
    out.append("| --- | --- |")
    for title, names in GROUPS:
        present = [n for n in names if n in records]
        grouped.update(present)
        out.append(f"| {title} | {', '.join(f'`{n}`' for n in present)} |")
    rest = sorted(set(records) - grouped)
    if rest:
        out.append(f"| Прочее | {', '.join(f'`{n}`' for n in rest)} |")

    out.append("\n## Полная опись\n")
    out.append("| Файл | Байт | Шифр | Имя | Описание |")
    out.append("| --- | ---: | --- | --- | --- |")
    for name in sorted(records):
        rec = records[name]
        desc = rec["desc"].replace("|", "\\|")
        out.append(
            f"| `{name}` | {rec['size']} | {rec['shifr']} | "
            f"{rec['ime']} | {desc} |"
        )

    result = "\n".join(out) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(result)
        print(f"записано: {args.output} ({len(records)} записей)")
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
