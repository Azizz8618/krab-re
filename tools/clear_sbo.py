#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clear_sbo.py — освобождение сбойных зон номера без администратора.

Файлы на сбойных зонах (СБЗ) переживают сеанс: они принадлежат паре
«номер + терминал» и держат комплект зон до истечения срока хранения
(1—4 суток, задаётся Генератором). Из-за этого файлы накапливаются от
прогона к прогону, а при исчерпании комплектов система отвечает
«НЕТ ЗОН ДЛЯ УПРЯТ».

Способ без прав администратора: открыть файл директивой ИМЯ (файл
поднимается на рабочее поле) и завершить сеанс директивой КОН — по
описанию ШКО101 «если у вас был файл на сбойных зонах, то он пропадает».
Директива ВЫХ здесь не помогает: она относится к программе ЛИСТ, а не
к Монитору абонентов («НЕТ ДИРЕК»).

Запуск:
    python3 tools/clear_sbo.py                # номер 1234, ключ 1234
    python3 tools/clear_sbo.py --list         # только показать список
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from krab_session import KEY, USER, KrabSession, fold  # noqa: E402


def list_files(kr: KrabSession) -> list[str]:
    """Имена файлов на сбойных зонах по директиве СБО."""
    out = kr.directive("сбо", timeout=45)
    names: list[str] = []
    for line in out.splitlines():
        # «СИПРОД  123400 Б-3 Т-02» — первое слово строки и есть имя
        m = re.match(r"^\s*([А-ЯЁ][А-ЯЁа-яё0-9]{1,7})\s+\d{4,6}\b", line)
        if m and m.group(1) != "СБО":
            names.append(m.group(1))
    # список печатается по терминалам — одинаковые имена повторяются
    return list(dict.fromkeys(names))


def main() -> int:
    parser = argparse.ArgumentParser(description="Очистка сбойных зон")
    parser.add_argument("--user", default=USER, help="шифр номера")
    parser.add_argument("--key", default=KEY, help="ключ номера")
    parser.add_argument("--list", action="store_true", help="только список")
    parser.add_argument("--rounds", type=int, default=12,
                        help="сколько раз повторять цикл ИМЯ+КОН")
    args = parser.parse_args()

    kr = KrabSession()
    print(f"линия: {'КВУ 4198' if kr.serial else 'ДКС'}")
    kr.login(args.user, args.key)
    try:
        for round_no in range(1, args.rounds + 1):
            files = list_files(kr)
            print(f"раунд {round_no}: на сбойных зонах {len(files)} — "
                  f"{', '.join(files) if files else '(пусто)'}")
            if not files:
                print("сбойные зоны свободны")
                return 0
            if args.list:
                return 0
            # по одному файлу за сеанс: после КОН линия успевает освободиться,
            # а набранное по символам имя не искажается
            # имя, записанное неверным набором, набрать нельзя —
            # такие остаются до истечения срока хранения
            clean = [n for n in files
                     if n.upper() == fold(n).upper() and n.isalpha()]
            if not clean:
                print("все имена искажены — чистить вручную")
                return 1
            name = clean[0]
            answer = kr.directive(f"имя {name}", timeout=25)
            print(f"  ИМЯ {name}: {' | '.join(answer.splitlines()[-2:])[:70]}")
            kr.directive("кон", timeout=30)      # файл на СБЗ пропадает
            time.sleep(5)
            kr.reconnect()                        # после КОН старая линия мертва
            kr.login(args.user, args.key)
    finally:
        try:
            kr.close()
        except Exception:
            pass
    print("цикл исчерпан, список не пуст — возможно, срок хранения не истёк")
    return 1


if __name__ == "__main__":
    sys.exit(main())