"""Работоспособность директив Монитора абонентов КРАБ.

Пользователь 1234 / ключ 1234, терминал 15ИЭ-00-013 (эмулятор ie15).
Ответы сняты с живой машины (BEP.19 ОТ 27.11.92):

    ТЕР  ->  ЭВМ-3  К-20 | ФИЗТЕР: КВУ  Н-020 | СЕТЬ:НЕТ
    ВРЕ  ->  dd.mm.yy  ВРЕМЯ hh.mm.ss  (ВЕР.19 ОТ 27.11.92)
    КТО  ->  01 (20) КВУ-020 123400  ГОСТЬ
    КЛ   ->  НЕВЕРНЫЙ НОМЕР
    ДЛИ  ->  НЕТ ИМЕНИ МАССИВА   (текущий файл не образован)
    СОС  ->  НЕТ ИМЕНИ МАССИВА
    ЧТО  ->  У ВАС НЕТ ПЗ
    ГДЕ  ->  У ВАС НЕТ ПЗ
    ШКО  ->  справка: МА, ЛИСТ, БЮДЖЕТ, СТАТ, СЕРВИС; выход блока — «#»

Запуск: python3 -m pytest tests/ -k directives -v
"""
from __future__ import annotations

import unittest

from krab_session import USER, KrabSession, fold


class Directives(unittest.TestCase):
    """Одна линия на весь класс: вход один раз, дальше только директивы."""

    @classmethod
    def setUpClass(cls):
        cls.kr = KrabSession()
        cls.kr.login_or_skip()
        cls.kr.cleanup()

    @classmethod
    def tearDownClass(cls):
        cls.kr.cleanup()
        cls.kr.close()

    # --- справочные директивы ------------------------------------------
    def test_01_ter(self):
        """ТЕР: номер машины и терминала, тип линии."""
        out = self.kr.directive("тер")
        self.assertIn("ТЕР", out)
        self.assertIn("ЭВМ", out)
        self.assertIn("ФИЗТЕР", out)
        self.assertIn("КВУ", out)                # линия КВУ, не АС

    def test_02_vre(self):
        """ВРЕ: дата, время, версия системы."""
        out = self.kr.directive("вре")
        self.assertIn("ВРЕМЯ", out)
        self.assertIn("ВЕР.19", out)
        self.assertIn("27.11.92", out)

    def test_03_kto(self):
        """КТО: наш пользователь среди работающих — 123400 ГОСТЬ."""
        out = self.kr.directive("кто")
        self.assertIn("123400", out)
        self.assertIn("ГОСТЬ", out)
        self.assertIn("КВУ", out)

    def test_04_kl(self):
        """КЛ без параметра — неинициализированный номер: НЕВЕРНЫЙ НОМЕР."""
        out = self.kr.directive("кл")
        self.assertIn("НЕВЕРНЫЙ НОМЕР", out)

    # --- директивы, которым нужен текущий файл -------------------------
    def test_05_dli_bez_massiva(self):
        """ДЛИ без образованного файла: НЕТ ИМЕНИ МАССИВА."""
        out = self.kr.directive("дли")
        self.assertIn("НЕТ ИМЕНИ МАССИВА", out)

    def test_06_sos_bez_massiva(self):
        """СОС (состояние файла) без имени массива тоже отказ."""
        out = self.kr.directive("сос")
        self.assertIn("НЕТ ИМЕНИ МАССИВА", out)

    # --- подчинённые задачи --------------------------------------------
    def test_07_chto_bez_pz(self):
        """ЧТО без подчинённой задачи: У ВАС НЕТ ПЗ."""
        out = self.kr.directive("что")
        self.assertIn("У ВАС НЕТ ПЗ", out)

    def test_08_gde_bez_pz(self):
        """ГДЕ без параметра тоже говорит про отсутствие ПЗ."""
        out = self.kr.directive("где")
        self.assertIn("У ВАС НЕТ ПЗ", out)



if __name__ == "__main__":
    unittest.main(verbosity=2)


class SchoolBlock(unittest.TestCase):
    """Блок Школы и повторный вход — в СВОЁМ сеансе.

    В общем сеансе класса Школа «залипает»: эхо директив идёт, а ответы
    приходят с задержкой в минуты, и проверки Школы падают по таймауту
    (проверено 18.10.2026). В свежем сеансе Школа отвечает за секунды,
    поэтому эти проверки выполняются на отдельном входе.
    """

    @classmethod
    def setUpClass(cls):
        cls.kr = KrabSession()
        cls.kr.login_or_skip()

    @classmethod
    def tearDownClass(cls):
        cls.kr.close()

    def test_01_shko_spravka(self):
        """ШКО выдаёт общую справку и список инструкций."""
        out = self.kr.directive("шко", timeout=90)
        self.assertIn("СИСТЕМА КРАБ ПРЕДСТАВЛЯЕТ СОБОЙ КОМПЛЕКС", out)
        self.assertIn("ШКО ИНС", out)

    def test_02_shko_ins_ma(self):
        """ШКО ИНС МА настраивает школу на Монитор абонентов."""
        self.kr.directive("шко инс ма", timeout=90)
        # «шко дир» печатает справку о пяти группах; список директив
        # группы ВХОДА-ВЫХОДА — по «шко дир вх», там есть НАЧ.
        # Директивы Школа печатает с разрядкой («Н А Ч»), описания
        # слитно — сверяем по описанию директивы НАЧ.
        out = self.kr.directive("шко дир вх", timeout=90)
        self.assertIn("НАЧАЛО РАБОТЫ", out)

    def test_03_kon_vozvrashchaet_v_monitor(self):
        """КОН из блока Школы возвращает в Монитор абонентов.

        Это и есть штатный выход из Школы: приглашение меняется с «#»
        на «-», номер остаётся открытым — следующая директива работает.
        """
        self.kr.exit()
        out = self.kr.directive("тер", timeout=60)
        self.assertIn("ФИЗТЕР", out)

    def test_04_kon_zakryvaet_nomer_i_povtorny_vhod(self):
        """КОН из Монитора закрывает номер, повторный вход работает."""
        out = self.kr.exit()
        self.assertIn("КОНЕЦ СЕАНСА", out)
        # КРАБ уже вызван (номер закрыт, система осталась) — достаточно
        # войти заново, «краб» набирать не нужно
        self.kr.enter()
        out = self.kr.directive("тер", timeout=60)
        self.assertIn("ФИЗТЕР", out)
        self.kr.exit()
