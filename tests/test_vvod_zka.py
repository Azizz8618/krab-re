"""Загрузка документа в КРАБ с перфокарт (задача ЗКА, шифр 410300).

Шаблон колоды — `VVOD/vvod_dubna.txt`: шапка паспорта

    ШИФР 410300^ / ОЗУ 32^ / ТЕЛЕ^ / tap 60(2148)^ / дис 57(2048)^ /
    АЦП 128^ / ВХО 1^ / ВРЕ 1^ / ЕВ1

и хвост

    ЕКОНЕЦ / ``````

Текст документа вставляется МЕЖДУ шапкой и хвостом. Колода подключается к
устройству ввода ОС ДИСПАК (vu0) и подаётся сигналом FS8; результат —
файл на сбойных зонах КРАБ, который виден директивой СБО.

Запуск: python3 -m pytest tests/test_vvod_zka.py -v
"""
from __future__ import annotations

import subprocess
import time
import unittest
from pathlib import Path

from krab_session import KrabSession

#: шаблон колоды и рабочий каталог ввода ОС ДИСПАК
VVOD = Path.home() / "Yandex.Disk" / "simh" / "BESM6" / "VVOD"
TEMPLATE = VVOD / "vvod_dubna.txt"
DECK = VVOD / "zka_test.txt"
TMUX = "besm6:0"

#: текст проверяемого документа
DOCUMENT = (
    "ПРОВЕРКА ЗАГРУЗКИ ДОКУМЕНТА С ПЕРФОКАРТ",
    "ВТОРАЯ СТРОКА ТЕСТОВОГО ДОКУМЕНТА",
)


def simh_console(commands, hold: float = 2.0) -> None:
    """Подать команды в консоль SIMH (tmux) и продолжить счёт.

    Прерывание в этой конфигурации — символ 0x07 (`set console wru=7`),
    а не Ctrl+E. Последняя команда — «go», счёт возобновляется.
    """
    subprocess.run(["tmux", "send-keys", "-t", TMUX, "-H", "07"],
                   check=True, capture_output=True)
    time.sleep(hold)
    for cmd in commands:
        subprocess.run(["tmux", "send-keys", "-t", TMUX, cmd],
                       check=True, capture_output=True)
        subprocess.run(["tmux", "send-keys", "-t", TMUX, "Enter"],
                       check=True, capture_output=True)
        time.sleep(0.8)


def build_deck() -> str:
    """Колода из шаблона с текстом документа между шапкой и хвостом."""
    lines = TEMPLATE.read_text(encoding="utf-8").split("\n")
    head_end = next(i for i, x in enumerate(lines) if x.strip() == "ЕВ1") + 1
    tail_start = next(i for i, x in enumerate(lines) if x.strip() == "ЕКОНЕЦ")
    return "\n".join(lines[:head_end] + list(DOCUMENT) + lines[tail_start:])


def sbo_files(kr: KrabSession) -> set[str]:
    """Имена файлов на сбойных зонах по директиве СБО."""
    import re
    out = kr.directive("сбо", timeout=45)
    names = set()
    for line in out.splitlines():
        m = re.match(r"^\s*([А-ЯЁA-Z][А-ЯЁA-Za-z0-9]{1,5})\s+\d{4,6}\s+"
                     r"(?:Б|T)-\d", line)
        if m:
            names.add(m.group(1))
    return names


def task_in_queue(kr_serial: bool = False) -> bool:
    """Есть ли задача 410300 в очереди ОС (НОМ на операторской консоли)."""
    from krab_session import KrabSession, SERIAL_PORT
    kr = KrabSession(SERIAL_PORT)
    try:
        kr.serial = True
        kr.term.drain(quiet=0.5, timeout=8)
        kr.term.link.send(b"HYC\x03")
        kr.term.wait_quiet(1.5, 20)
        kr.term.type("ном")
        kr.term.key("KEY_ENTER")
        kr.term.wait_quiet(2.5, 25)
        text = kr.term.screen()
        return "410300" in text
    finally:
        try:
            kr.close()
        except Exception:
            pass


def feed_deck(path: Path, tries: int = 4, pause: float = 25.0) -> bool:
    """Подать колоду в ОС и дождаться приёма.

    ОС отвечает `ЗМЛ0` — замятием ввода. Это периодическая ошибка, она
    возникает и на реальной машине; в эмуляторе чаще, потому что счёт идёт
    быстрее. Поэтому после каждого сигнала FS8 ждём паузу и проверяем
    очередь (`НОМ`), повторяя при необходимости. Слишком частые повторы
    замятие не убивают — нужно давать машине время.
    """
    for attempt in range(tries):
        simh_console([
            "detach vu0",
            f"at vu0 {path}",
            "d 6 1",
            "d 5 10",
            "set cpu req",
            "go",
        ], hold=3.0)
        time.sleep(pause)
        if task_in_queue():
            return True
    return False


class LoadFromCards(unittest.TestCase):
    """Документ с перфокарт оказывается на сбойных зонах КРАБ."""

    def setUp(self):
        self.kr = KrabSession()
        self.kr.login_or_skip()
        self.kr.cleanup()

    def tearDown(self):
        self.kr.cleanup()
        self.kr.close()

    def test_01_dokument_s_kart_okazivaetsya_na_sbo(self):
        """Ввод колоды с документом даёт новый файл на сбойных зонах."""
        deck = build_deck()
        DECK.write_text(deck, encoding="utf-8")
        self.assertIn("ПРОВЕРКА ЗАГРУЗКИ ДОКУМЕНТА С ПЕРФОКАРТ", deck)

        before = sbo_files(self.kr)

        # колода подаётся с повторами: ОС отвечает замятием ввода (ЗМЛ0)
        self.assertTrue(feed_deck(DECK),
                        "колода не принята: задача 410300 не появилась в очереди")

        # задача отрабатывает, результат — файл на сбойных зонах КРАБ
        for _ in range(8):
            time.sleep(10)
            fresh = sbo_files(self.kr) - before
            if fresh:
                return
        self.assertTrue(fresh,
                        f"новых файлов на сбойных зонах нет: {sbo_files(self.kr)}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
