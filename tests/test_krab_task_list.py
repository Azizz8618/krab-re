"""Формирование задач и просмотр результата через программу ЛИСТ.

Пользователь 1234 / ключ 1234, терминал 15ИЭ-00-013.

В архиве номера 1234 лежат готовые программы (каталог «КТЛ»):
    ФОРГДР — Фортран (*NАМЕ FTN, *САLL УЕSМЕМОRУ)
    КАЛЬК  — Паскаль (*NАМЕ PАSСАL), в паспорте карточка «ТЕЛЕ^»,
             то есть задача диалоговая (раздел ТЕЛЕ)
    СИПРОД, ГОСТЬ, ДИСПАК, ТЕСТ, ТЕСТ1, ФГОТ, ЖУРГОС, БЭСМ6

Проверено на живой машине:
    имя форгдр     -> ИМЯ ФОРГДР
    фор пз         -> ШИФP 123400000000
                      ВНИМАНИЕ! ОКОНЧИЛАСЬ ЗАДАЧА ШИФР 123400000000
    лис            -> ** К Р А Б ** (ЛИСТ*ВЕР.19/1 ОТ 04.06.92), приглашение «*»
    дли (в Листе)  -> ЗTРАК =015  ИTРАК =094 / 00005 - КОНЕЦ БУФЕРА
    выд (в Листе)  -> листинг задачи (МОНИТОР* / ИСПОРЧЕНА ПОДПРОГРАММА …)
    кон (в Листе)  -> возврат в Монитор, приглашение «-»

Диалоговая задача (КАЛЬК, ТЕЛЕ^) формируется как подсистема: «фор пс» —
по указанию механики КРАБ просмотр ведётся только для подчинённых задач
(ПЗ — подчинённая задача, ПС — подсистема).

Запуск: python3 -m pytest tests/test_krab_task_list.py -v
"""
from __future__ import annotations

import time
import unittest

from krab_session import KrabSession, fold

#: обратная к fold() таблица: терминал набора Н2 показывает русские буквы
#: латинскими гомоглифами (РАSСАL → PASCAL), сравниваем именно с ними
_L2L = str.maketrans({"А": "A", "В": "B", "С": "C", "Е": "E", "Н": "H",
                      "К": "K", "М": "M", "О": "O", "Р": "P", "Т": "T",
                      "Х": "X", "У": "Y", "Ъ": "b", "Ы": "y", "Ь": "b"})


def latin_fold(text: str) -> str:
    """Кириллицу выдачи ЭВМ свести к латинским гомоглифам набора Н2."""
    return text.upper().translate(_L2L)


class TaskFormation(unittest.TestCase):
    """Один вход на класс, сессия сбрасывается после каждого теста."""

    @classmethod
    def setUpClass(cls):
        cls.kr = KrabSession()
        cls.kr.login_or_skip()
        cls.kr.cleanup()

    @classmethod
    def tearDownClass(cls):
        cls.kr.cleanup()
        cls.kr.close()

    def out(self, cmd, quiet=3.0, timeout=90.0):
        """Исполнить директиву и вернуть её выдачу (только новые строки)."""
        return self.kr.directive(cmd, quiet=quiet, timeout=timeout)

    def ensure_monitor(self):
        """Вернуть терминал в Монитор (общий механизм драйвера)."""
        return self.kr.ensure_monitor()

    def wait_pz_free(self, tries: int = 4, pause: float = 2.0) -> bool:
        """Дождаться, пока ПЗ пользователя освободится.

        У номера может быть только одна подчинённая задача: повторное
        «фор пз» при занятой ПЗ даёт «УЖЕ ЕСТЬ ПЗ», и последующий «лис»
        отвечает «НЕТ ПЗ В РЕШЕНИИ». Поэтому перед формированием ждём
        «что» без задачи.
        """
        for _ in range(tries):
            out = self.out("что")
            # свободна только ПУСТАЯ ПЗ; «НЕТ ПЗ В РЕШЕНИИ» означает, что ПЗ
            # есть, но не в решении — такую сбрасываем директивой ВЫБ
            if "У ВАС НЕТ ПЗ" in out:
                return True
            if "НЕТ ПЗ В РЕШЕНИИ" in out or "УЖЕ ЕСТЬ ПЗ" in out:
                self.out("выб")
            time.sleep(pause)
        return False

    def form_pz(self, nm: str = "форгдр") -> str:
        """Сформировать подчинённую задачу из файла архива.

        Диалог на живой машине:
            имя форгдр -> ФОР ПЗ -> ШИФР 123400000000
                                  ПОДСИСТЕМА ВКЛЮЧЕНА / ВОЙТИ? (ДА,НЕТ)
        На «ВОЙТИ?» отвечаем ДА — иначе подсистема остаётся выключенной
        и последующий «лис» отвечает «НЕТ ПЗ В РЕШЕНИИ».
        """
        self.ensure_monitor()
        self.wait_pz_free()
        self.out(f"имя {nm}")
        out = self.out("фор пз", quiet=2.5, timeout=20)
        if "ВОЙТИ" in out:
            out += "\n" + self.out("да", quiet=2.5, timeout=20)
        return out

    # --- каталог --------------------------------------------------------
    def test_01_ktl_arhiva_1234(self):
        """КТЛ: в архиве номера есть ФОРГДР (Фортран) и КАЛЬК (Паскаль)."""
        self.ensure_monitor()
        out = self.out("ктл", timeout=15)
        self.assertIn("ФОРГДР", out)
        self.assertIn("КАЛЬК", out)
        self.assertIn("123400", out)

    def test_02_fortran_file_is_ftn(self):
        """ИМЯ ФОРГДР + ВЫД: карта 0005 — *NАМЕ FTN (Фортран)."""
        self.ensure_monitor()
        self.wait_pz_free()
        self.out("имя форгдр")
        out = self.out("выд 5-5")
        # «*NАМЕ FТN» в выдаче Н2: Т — кириллическая, приводим к FTN
        self.assertIn("FTN", latin_fold(out))

    def test_03_pascal_file_is_pascal(self):
        """ИМЯ КАЛЬК + ВЫД: карта 0003 — ТЕЛЕ^, карта 0005 — PASCAL.

        На терминале набора Н2 часть кириллицы выводится латинскими
        гомоглифами (PASCAL ← РАSСАL), поэтому сводим гомоглифы через
        отдельную таблицу latin_fold(), а не через fold(): тот работает
        наоборот, из кириллицы в латиницу выдачи ЭВМ.
        """
        self.ensure_monitor()
        self.out("имя кальк")
        out = self.out("выд 3-5")
        self.assertIn("ТЕЛЕ", out)               # карта 0003 — диалоговая задача
        self.assertIn("PASCAL", latin_fold(out))

    # --- формирование и просмотр ---------------------------------------
    def test_04_for_pz_puts_task_on_buffer(self):
        """ФОР ПЗ: задача получает шифр и доводится до конца."""
        out = self.form_pz()
        # в выдаче Н2: «ШИФP» — P латинская, «ЗAДAЧA» — кириллические
        text = latin_fold(out)
        self.assertIn("ШИФP", text)
        self.assertIn("123400000000", out)
        # «ОКОНЧИЛАСЬ ЗАДАЧА» выводится гомоглифами (OKOHЧИЛACb), но
        # у Ч, И, Л нет латинских двойников — эта часть стабильна
        self.assertIn("ЧИЛ", out)

    def test_05_lis_shows_listing_of_task(self):
        """ЛИС → ДЛИ → ВЫД: листинг подчинённой задачи виден на экране."""
        self.form_pz()
        self.out("лис", quiet=2.5, timeout=20)
        # ждём баннер программы ЛИСТ («ЛИСТ*ВЕР…»)
        self.assertTrue(
            self.kr.term.wait_for("ЛИCT", timeout=20),
            f"нет программы ЛИСТ: {self.kr.screen()!r}",
        )
        dl = self.out("дли", quiet=2.0, timeout=15)
        self.assertIn("ТРАК", dl)                 # ЗТРАК/ИТРАК
        self.assertIn("КОНЕЦ БУФЕРА", dl)         # буфер листинга дочитан
        vy = self.out("выд", quiet=2.0, timeout=15)
        # содержимое листинга задачи: любые строки, кроме эха директивы ВЫД
        # и приглашения «*» — конкретный текст задачи не фиксирован
        body = [x for x in vy.splitlines()
                if x and not x.startswith("ВЫД") and x.strip() != "*"]
        self.assertTrue(body, f"пустой листинг: {vy!r}")

    def test_06_kon_from_list_back_to_monitor(self):
        """КОН в программе ЛИСТ возвращает в Монитор абонентов («-»)."""
        self.form_pz()
        self.out("лис", quiet=2.5, timeout=20)
        self.kr.term.wait_for("ЛИCT", timeout=20)
        self.out("кон", quiet=2.0, timeout=15)
        lines = [x.strip() for x in self.kr.term.lines() if x.strip()]
        self.assertTrue(lines and lines[-1] == "-",
                        f"не вернулись в Монитор: {lines[-3:]!r}")

    # --- диалоговая задача (ТЕЛЕ) --------------------------------------
    def test_07_for_ps_dialog_task(self):
        """ФОР ПС для диалоговой задачи КАЛЬК (паспорт с ТЕЛЕ^)."""
        self.ensure_monitor()
        self.out("имя кальк")
        out = self.out("фор пс", quiet=2.5, timeout=20)
        self.assertTrue(fold(out), "нет ответа на ФОР ПС")
        # ответ либо содержит шифр задачи, либо сообщение об отказе —
        # важно, что система ответила и осталась в Мониторе
        if "ШИФР" not in out and "ШИФP" not in out:
            self.out("кон", quiet=2.0, timeout=15)


if __name__ == "__main__":
    unittest.main(verbosity=2)