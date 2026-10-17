"""Доступ в Монитор абонентов КРАБ: пользователь 1234 / ключ 1234,
терминал 15ИЭ-00-013 (эмулятор ie15, линия ДКС БЭСМ-6).

Протокол входа проверен на живой машине (BEP.19 ОТ 27.11.92):

    краб   ->  ** K  P  A  B **  (BEP.19 ОT 27.11.92)  и приглашение «-»
    нач    ->  «КТО?»
    шифр   ->  «КЛЮЧ-»
    ключ   ->  сеанс открыт (и сообщение о файлах на сбойных зонах, если есть)
    кон    ->  выход из номера, приглашение «-»

Запуск: python3 -m pytest tests/ -k entry -v
"""
from __future__ import annotations

import unittest

from krab_session import KEY, USER, KrabSession, fold


class MonitorAccess(unittest.TestCase):
    """Одна линия на весь класс: частые переподключения линию дёргают."""

    @classmethod
    def setUpClass(cls):
        cls.kr = KrabSession()
        cls.kr.login()

    @classmethod
    def tearDownClass(cls):
        cls.kr.close()

    # --- запуск системы ------------------------------------------------
    def test_01_banner(self):
        """Вызов «краб» даёт баннер, версию и приглашение директивы."""
        text = self.kr.start()
        self.assertIn("К  Р  А  Б", text)
        self.assertIn("ВЕР.", text)              # (ВЕР.19 ОТ 27.11.92)
        self.assertIn("27.11.92", text)

    def test_02_nach_zapros_kto(self):
        """«нач» запрашивает номер пользователя приглашением КТО?."""
        self.kr.send("нач")
        text = self.kr.wait_prompt("КТО?")
        self.assertIn("КТО?", text)

    def test_03_kto_zapros_klyuch(self):
        """Шифр принят — система запрашивает ключ (КЛЮЧ-)."""
        self.kr.send(USER)
        text = self.kr.wait_prompt("КЛЮЧ")
        self.assertIn("КЛЮЧ-", text)

    def test_04_vhod_s_klyuchom(self):
        """Ключ 1234 открывает сеанс: приглашение «-» и идентификация."""
        out = self.kr.send(KEY)
        self.assertIn("-", out)
        # пользователь 1234 в системе КТО виден как 123400 ГОСТЬ
        kto = self.kr.directive("кто")
        self.assertIn("123400", kto)
        self.assertIn("ГОСТЬ", kto)

    def test_05_kon_zakryvaet_seans(self):
        """КОН закрывает номер и возвращает к приглашению ЭВМ."""
        out = self.kr.exit()
        self.assertIn("КОН", out)
        self.assertIn("-", out)

    # --- отказы ---------------------------------------------------------
    def test_06_nevernyy_klyuch_zapreshchaet_vhod(self):
        """Дважды неверный ключ — вход запрещён (НЕВЕРНЫЙ КЛЮЧ)."""
        self.kr.send("нач")
        self.kr.wait_prompt("КТО?")
        self.kr.send(USER)
        self.kr.wait_prompt("КЛЮЧ")
        self.kr.send("9999")                     # заведомо неверный ключ
        self.kr.send("9999")
        text = self.kr.screen()
        self.assertIn("НЕВЕРНЫЙ КЛЮЧ", fold(text))

    def test_07_neizvestnyy_nomer(self):
        """Незарегистрированный номер не пропускается на запрос ключа."""
        self.kr.send("нач")
        self.kr.wait_prompt("КТО?")
        self.kr.send("999999")
        # ответ смотрим только в новых строках: экран держит историю
        text = self.kr.wait_prompt("ВЫ НЕ ПОЛЬЗОВАТЕЛЬ", timeout=30)
        self.assertIn("ВЫ НЕ ПОЛЬЗОВАТЕЛЬ ЭВМ", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
