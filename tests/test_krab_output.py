"""Вывод содержимого файла (АЦП/ПК/ПЛ) и правка массива (МАС).

Проверяются директивы, которые до этого не прогонялись на живой машине.
Формы взяты из первоисточников (Школа и код; номера строк — в
`docs/EDITING.md`, раздел «Ещё не покрыто тестами»):

    АЦ[П] [<ТИПВЫВ>] [<ШИФР>]      типы ПН/ПБ/РН/РБ/ЛН/ЛБ, /<КСТР> строк в листе
    ПК [<ТИПВЫВ>] [<ШИФР>]         кодировки УПП/УПДК/ЕС/СДС
    ПЛ [<ШИФР>]                    без типа
    <ПД> М[АС] <НАЗВАН> [<ХОЗЯИН>] строки файла вместо строки, введённой на «+»

Запуск: python3 -m pytest tests/test_krab_output.py -v
"""
from __future__ import annotations

import time
import unittest
from pathlib import Path

from krab_session import KrabSession

#: АЦПУ БЭСМ-6: файл, куда эмулятор пишет центральную печать
ACPU = Path.home() / "Yandex.Disk" / "simh" / "BESM6" / "ACPU" / "output.txt"
#: перфокарты и перфолента (см. dispak.ini: vu0 и pl0)
CARDS = Path.home() / "Yandex.Disk" / "simh" / "BESM6" / "UVU" / "punchcard.txt"
TAPE = Path.home() / "Yandex.Disk" / "simh" / "BESM6" / "UVU" / "punch.txt"

#: отказы, которыми гость может получить печать вместо задачи
DENIED = ("НЕ ИМЕЕТЕ ПРАВА", "НЕТ БЮДЖЕТА", "ЗАПРЕЩ", "НЕТ МЕСТА")


def _size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def _make(kr: KrabSession, lines) -> str:
    """Образовать текущий файл с указанными строками (хелпер из набора правки)."""
    from test_krab_edit_form import make_file
    return make_file(kr, tuple(lines))


def _cards(kr: KrabSession) -> int:
    from test_krab_edit_form import cards_of
    return cards_of(kr)


class OutputDirectives(unittest.TestCase):
    """АЦП, ПК, ПЛ — печать и перфорация текущего файла."""

    @classmethod
    def setUpClass(cls):
        cls.kr = KrabSession()
        cls.kr.login_or_skip()
        cls.kr.cleanup()

    @classmethod
    def tearDownClass(cls):
        cls.kr.cleanup()
        cls.kr.close()

    def _vydacha(self, cmd: str, path: Path, timeout: float = 60.0) -> str:
        """Выполнить вывод и проверить признак успеха по файлу устройства.

        Успех — рост файла устройства (АЦПУ, перфокарты, перфолента).
        Если вывода нет, ответ должен быть одним из отказов: у гостя без
        бюджета печать может быть запрещена, и тест это фиксирует.
        """
        _make(self.kr, ("один", "два"))
        before = _size(path)
        out = self.kr.directive(cmd, timeout=timeout)
        time.sleep(3)
        after = _size(path)
        if after <= before:
            self.assertTrue(any(x in out for x in DENIED),
                            f"вывода нет, но и отказа не видно: {out!r}")
        return out

    def test_01_pechat_bez_fayla(self):
        """Без текущего файла печать отвергается.

        По коду (`FPRN:123`–131) сначала проверяется наличие текущего файла
        и его непустота, поэтому ожидаем `НЕТ ИМЕНИ МАССИВА` или `МАССИВ ПУСТ`.
        """
        out = self.kr.directive("ацп", timeout=45)
        self.assertTrue("НЕТ ИМЕНИ МАССИВА" in out or "МАССИВ ПУСТ" in out,
                        f"неожиданный ответ АЦП: {out!r}")

    def test_02_nevernyy_tip(self):
        """Неверный тип вывода распознаётся до постановки задачи."""
        _make(self.kr, ("один", "два"))
        out = self.kr.directive("ацп хх", timeout=45)
        self.assertIn("НЕВЕРНЫЙ ТИП ВЫВОД", out)

    def test_03_pechat_pn(self):
        """`АЦП ПН` — две колонки с номерами на центральный АЦПУ."""
        self._vydacha("ацп пн", ACPU)

    def test_04_perforaciya_upp(self):
        """`ПК УПП` — перфорация карт в кодировке УПП БЭСМ-6."""
        self._vydacha("пк упп", CARDS)

    def test_05_perfolenta(self):
        """`ПЛ` — перфолента; тип не задаётся (у неё его нет)."""
        out = self._vydacha("пл", TAPE)
        self.assertNotIn("НЕВЕРНЫЙ ТИП ВЫВОД", out)


class MacDirective(unittest.TestCase):
    """`МАС` — строки файла вместо строки, введённой на приглашение «+»."""

    @classmethod
    def setUpClass(cls):
        cls.kr = KrabSession()
        cls.kr.login_or_skip()
        cls.kr.cleanup()

    @classmethod
    def tearDownClass(cls):
        cls.kr.cleanup()
        cls.kr.close()

    def test_01_mas_bez_direktivy(self):
        """`МАС` сама по себе (без директивы редактирования) отвергается."""
        _make(self.kr, ("один", "два"))
        out = self.kr.directive("-мас бне1", timeout=45)
        self.assertTrue("НЕ БЫЛО ДИРЕКТИВЫ РЕДАКТИРОВАНИЯ" in out
                        or "НЕТ В КАТАЛОГЕ" in out
                        or "НЕТ ИМЕНИ МАССИВА" in out,
                        f"неожиданный ответ МАС: {out!r}")

    def test_02_mas_vstavlyaet_stroki_fayla(self):
        """После `ДОП` строка `-мас <файл>` подставляет строки файла.

        Файл-источник лежит на сбойных зонах (у гостя нет места в архиве),
        поэтому возможны два исхода: строки подставлены (карт больше) или
        источник не найден — тогда ответ `НЕТ В КАТАЛОГЕ`.
        """
        src = _make(self.kr, ("альфа", "бета"))
        _make(self.kr, ("один", "два"))
        before = _cards(self.kr)
        self.kr.directive("доп")
        self.kr.wait_new("+", timeout=40)
        out = self.kr.directive(f"-мас {src}", timeout=60)
        self.kr.directive("", timeout=20)
        after = _cards(self.kr)
        if after > before:
            self.assertGreaterEqual(after, before + 2)
        else:
            self.assertIn("НЕТ В КАТАЛОГЕ", out)

    def test_03_bez_priznaka_stroka_tekst(self):
        """Без признака директивы строка `мас …` идёт в файл как текст."""
        src = _make(self.kr, ("альфа", "бета"))
        _make(self.kr, ("один",))
        before = _cards(self.kr)
        self.kr.directive("доп")
        self.kr.wait_new("+", timeout=40)
        self.kr.directive(f"мас {src}", timeout=45)
        self.kr.directive("", timeout=20)
        self.assertGreater(_cards(self.kr), before,
                           "строка без признака должна была стать текстом")


if __name__ == "__main__":
    unittest.main(verbosity=2)
