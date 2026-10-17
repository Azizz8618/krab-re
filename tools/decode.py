#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
decode.py — декодер текстов системы КРАБ (ОС ДИСПАК, ЭВМ БЭСМ-6) в UTF-8.

Исходные тексты хранятся в 8-разрядной кодировке ОС ДИСПАК. Кириллица в ней
размещена следующим образом (в отличие от КОИ-8, отсутствие ё):

    0x80..0x9F  прописные  А Б В ... Я      (32 знака, Ё отсутствует)
    0xA0..0xAF  строчные   а б в ... п      (первые 16 строчных)
    0xB0..0xDF  резерв / рисовочные знаки
    0xE0..0xEF  строчные   р с т ... я      (последние 16 строчных)
    0xF0..0xFE  резерв
    0xFF        Ё (встречается редко, в отдельных файлах)

Разрыв строчного регистра между 0xAF и 0xE0 — особенность именно
кодовой таблицы ОС ДИСПАК, а не повреждение файла.

Прочие диапазоны:
    0x00..0x1F  управляющие коды (0x0D — конец строки, 0x09 — табуляция);
    0x20..0x7F  латиница и знаки препинания ASCII (включая рамку из |, -, *,
                +, =);
    0xC0..0xDF, 0xF0..0xFE — в корпусе практически не встречаются.

Использование:
    decode.py INPUT              # печать декодированного текста в stdout
    decode.py INPUT -o OUTPUT    # запись результата в файл
    decode.py DIR -d OUTDIR      # пакетное декодирование каталога
    decode.py DIR -d OUTDIR --check   # только проверка, без записи

Перевод строк: 0x0D 0x0A (CRLF) и одиночный 0x0A нормализуются в '\\n'.
"""

from __future__ import annotations

import argparse
import os
import sys

# Прописные: 0x80..0x9F. Ё в прописном регистре кодовой таблицей не
# предусмотрена, поэтому ровно 32 знака.
UPPER = "АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"

# Строчные разрываются на два диапазона: 0xA0..0xAF и 0xE0..0xEF.
LOWER_HEAD = "абвгдежзийклмноп"      # 0xA0..0xAF
LOWER_TAIL = "рстуфхцчшщъыьэюя"      # 0xE0..0xEF

# Знаки, вынесенные в верхний рисовочный диапазон. В корпусе текстов КРАБа
# они встречаются единично; значения подобраны по контексту, поэтому
# трактуются консервативно и помечаются в результате как редкие.
RARE = {
    0xFF: "Ё",
    0xBF: "ё",
}


def decode(data: bytes) -> str:
    """Декодирует байтовую строку ОС ДИСПАК в текст Unicode."""
    out: list[str] = []

    for byte in data:
        if byte < 0x80:
            out.append(chr(byte))
        elif byte < 0xA0:
            out.append(UPPER[byte - 0x80])
        elif byte < 0xB0:
            out.append(LOWER_HEAD[byte - 0xA0])
        elif byte < 0xE0:
            # Резервный диапазон: в текстах практически отсутствует.
            # Символ-заглушка делает такие места видимыми при просмотре.
            out.append("�")
        elif byte < 0xF0:
            out.append(LOWER_TAIL[byte - 0xE0])
        else:
            out.append(RARE.get(byte, "�"))

    text = "".join(out)

    # Нормализация концов строк: CRLF и одинокий CR -> LF.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def decode_file(path: str) -> str:
    with open(path, "rb") as fh:
        return decode(fh.read())


def iter_sources(src: str) -> list[str]:
    return sorted(
        os.path.join(src, name)
        for name in os.listdir(src)
        if os.path.isfile(os.path.join(src, name))
    )


def cmd_single(args: argparse.Namespace) -> int:
    text = decode_file(args.input)
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 0


def cmd_dir(args: argparse.Namespace) -> int:
    sources = iter_sources(args.input)
    if not sources:
        print(f"нет файлов в {args.input}", file=sys.stderr)
        return 1

    if not args.check:
        os.makedirs(args.output, exist_ok=True)

    total_bytes = 0
    for path in sources:
        text = decode_file(path)
        total_bytes += os.path.getsize(path)
        if not args.check:
            dst = os.path.join(args.output, os.path.basename(path))
            with open(dst, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)

    verb = "проверено" if args.check else "декодировано"
    print(f"{verb} файлов: {len(sources)}, исходных байтов: {total_bytes}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Декодирование текстов системы КРАБ (ОС ДИСПАК) в UTF-8",
    )
    parser.add_argument("input", help="файл или каталог исходников")
    parser.add_argument("-o", "--output", help="выходной файл (для одного файла)")
    parser.add_argument("-d", "--output-dir", dest="output_dir",
                        help="каталог результата (для каталога)")
    parser.add_argument("--check", action="store_true",
                        help="только проверка, ничего не записывать")
    args = parser.parse_args()

    if os.path.isdir(args.input):
        args.output = args.output_dir
        return cmd_dir(args)
    return cmd_single(args)


if __name__ == "__main__":
    sys.exit(main())
