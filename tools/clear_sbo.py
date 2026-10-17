#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clear_sbo.py — освобождение сбойных зон номера без администратора.

Файлы на сбойных зонах (СБЗ) переживают сеанс держат комплект зон до
истечения срока хранения (ВРСБЗ = 2 суток по исходнику L1). Из-за этого
файлы накапливаются от прогона к прогону, и при исчерпании комплекта
директива ИМЯ отвечает «НЕТ ЗОН ДЛЯ УПРЯТ» на любой линии.

Способ без прав администратора — из самой Школы (SCU101, описание КОН):

    «ВНИМАНИЕ! ЕСЛИ У ВАС БЫЛ ФАЙЛ НА СБОЙНЫХ ЗОНАХ, ТО ОН ПРОПАДАЕТ»

то есть цикл `ИМЯ <файл>` → `КОН` (сеанс кончается, файл с СБЗ
уничтожается) → снова вход в номер. По одному файлу за сеанс.

Директива ВЫХ здесь не помогает: она относится к программе ЛИСТ, а не
к Монитору абонентов («НЕТ ДИРЕК»). УНЧ работает только с архивом
(«НЕТ В КАТАЛОГЕ» для файла, которого в архиве нет).

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

#: файлы, которые тестам нужны на месте (используются для ФОР через ИМЯ);
#: RFKMR — это «КАЛЬК», отрисованная латинскими гомоглифами
KEEP = {"ФОРГДР", "КАЛЬК", "RFIУ4", "RFKMR"}


def list_files(kr: KrabSession, user: str) -> list[str]:
    """Имена файлов на сбойных зонах по директиве СБО.

    Строка имеет вид «БТC913 123400 Б-3 Т-20»: имя, хозяин, комплект,
    терминал. Берём файлы только своего номера.
    """
    out = kr.directive("сбо", timeout=45)
    names: list[str] = []
    my_hoz = f"{user}00"                       # шифр номера + два нуля
    for line in out.splitlines():
        m = re.match(r"^\s*([А-ЯЁA-Z][А-ЯЁA-Za-z0-9]{1,5})\s+(\d{4,6})\s+"
                     r"(?:Б|T)-\d", line)
        if m and m.group(2) == my_hoz and m.group(1) != "СБО":
            names.append(m.group(1))
    # список печатается по терминалам — одинаковые имена повторяются
    return list(dict.fromkeys(names))


def main() -> int:
    parser = argparse.ArgumentParser(description="Очистка сбойных зон")
    parser.add_argument("--user", default=USER, help="шифр номера")
    parser.add_argument("--key", default=KEY, help="ключ номера")
    parser.add_argument("--list", action="store_true", help="только список")
    parser.add_argument("--rounds", type=int, default=30,
                        help="сколько раз повторять цикл ИМЯ+КОН")
    args = parser.parse_args()

    kr = KrabSession()
    print(f"линия: {'КВУ 4198' if kr.serial else 'ДКС'}")
    kr.login(args.user, args.key)
    try:
        for round_no in range(1, args.rounds + 1):
            files = list_files(kr, args.user)
            files = [n for n in files if fold(n).upper() not in KEEP]
            print(f"раунд {round_no}: на сбойных зонах {len(files)} — "
                  f"{', '.join(files) if files else '(пусто)'}")
            if not files:
                print("сбойные зоны свободны")
                return 0
            if args.list:
                return 0
            for name in files:
                # ИМЯ строчными: набор Н2 искажает ЗАГЛАВНЫЕ русские буквы
                # (в файл попадает мусор, машина отвечает «НЕВЕРНЫЙ НОМЕР»)
                # ШКО ИМЯ: «по директиве ИМЯ с именем текущего файла он
                # уничтожается, после чего начинается поиск» — первый вызов
                # ПОДНИМАЕТ файл с СБЗ (он становится текущим), второй
                # УНИЧТОЖАЕТ его и не находит: зона свободна.
                low = name.lower()
                answer = kr.directive(f"имя {low}", timeout=25)
                if "СО СБОЙНЫХ ЗОН" not in answer and "НЕТ В КАТАЛОГЕ" not in answer:
                    print(f"  ИМЯ {name}: отказ — "
                          " | ".join(answer.splitlines()[-2:])[:70])
                answer = kr.directive(f"имя {low}", timeout=25)
                ok = "НЕТ В КАТАЛОГЕ" in answer
                print(f"  {name}: {'уничтожен' if ok else 'ответ: ' + ' | '.join(answer.splitlines()[-2:])[:60]}")
            break
        files = list_files(kr, args.user)
        files = [n for n in files if fold(n).upper() not in KEEP]
        print(f"осталось: {len(files)}{'' if not files else ' — ' + ', '.join(files)}")
        return 0 if not files else 1
    finally:
        try:
            kr.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
