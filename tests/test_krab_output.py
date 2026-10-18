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
    """Образовать текущий файл; при сбое — повторить на чистом состоянии.

    Под нагрузкой (идёт печать АЦПУ) ДОП иногда не успевает за окнами
    ожидания — тогда создание файла повторяется один раз.
    """
    from test_krab_edit_form import make_file, _to_monitor
    last = None
    for attempt in range(2):
        try:
            return make_file(kr, tuple(lines))
        except AssertionError as exc:
            last = exc
            _to_monitor(kr)
    raise last


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

    def test_04_perforaciya_upp(self):
        """`ПК УПП` — задача перфорации формируется.

        Проверено 18.10.2026: директива принимается и отвечает
        `ШИФР <шифр задачи>`, но файл перфокарт (`UVU/punchcard.txt`) не
        растёт — устройств вывода на перфорацию в этой конфигурации ОС нет
        (в руководстве оператора для `ДАЙ`/`НЕТ` есть идентификаторы только
        `А` — АЦПУ, `Г` — ленты, `Д` — диски). Поэтому проверяется
        постановка задачи, а не выдача.
        """
        _make(self.kr, ("один", "два"))
        out = self.kr.directive("пк упп", timeout=60)
        self.assertIn("ШИФР", out)
        self.assertNotIn("НЕВЕРНЫЙ ТИП ВЫВОД", out)

    def test_05_perfolenta(self):
        """`ПЛ` — задача на перфоленту формируется (тип не задаётся)."""
        _make(self.kr, ("один", "два"))
        out = self.kr.directive("пл", timeout=60)
        self.assertIn("ШИФР", out)
        self.assertNotIn("НЕВЕРНЫЙ ТИП ВЫВОД", out)


class MacDirective(unittest.TestCase):
    """`МАС` — строки файла вместо строки, введённой на приглашение «+».

    Признак директивы в этой конфигурации — ТОЧКА: `УПД` отвечает `.`
    (проверено 18.10.2026), а описание в Школе (`ШКО МАС`) требует
    начинать строку с признака: `<ПД> М[АС] <НАЗВАН> [<ХОЗЯИН>]`.
    Поэтому подстановка вызывается как `.мас <имя>`, а строка `-мас …`
    или `мас …` без признака уходит в файл обычным текстом.
    """

    @classmethod
    def setUpClass(cls):
        cls.kr = KrabSession()
        cls.kr.login_or_skip()
        cls.kr.cleanup()

    @classmethod
    def tearDownClass(cls):
        cls.kr.cleanup()
        cls.kr.close()

    def test_01_priznak_direktivy(self):
        """`УПД` выдаёт признак директивы — точка (а не дефис)."""
        out = self.kr.directive("упд", timeout=45)
        self.assertIn(".", out)
        self.assertNotIn("НЕТ ДИРЕК", out)

    def test_02_mas_vstavlyaet_stroki_fayla(self):
        """После `ДОП` строка `.мас <файл>` подставляет строки файла.

        Файл-источник лежит на сбойных зонах (места в архиве у гостя нет),
        поэтому возможны два исхода: строки подставлены (карт больше на
        число строк файла) или источник не найден — `НЕТ В КАТАЛОГЕ`.
        """
        src = _make(self.kr, ("альфа", "бета"))
        _make(self.kr, ("один", "два"))
        before = _cards(self.kr)
        self.kr.directive("доп")
        self.kr.wait_new("+", timeout=40)
        out = self.kr.directive(f".мас {src}", timeout=60)
        self.kr.directive("", timeout=20)
        after = _cards(self.kr)
        if after > before:
            self.assertGreaterEqual(after, before + 2)
        else:
            self.assertIn("НЕТ В КАТАЛОГЕ", out)

    def test_03_bez_priznaka_podstanovki_net(self):
        """Без признака директивы подстановки строк файла не происходит.

        Строка `мас <файл>` (без ведущей точки) не подставляет строки
        файла: число карт не растёт на число строк источника.
        """
        src = _make(self.kr, ("альфа", "бета"))
        _make(self.kr, ("один",))
        before = _cards(self.kr)
        self.kr.directive("доп")
        self.kr.wait_new("+", timeout=40)
        self.kr.directive(f"мас {src}", timeout=45)
        self.kr.directive("", timeout=20)
        after = _cards(self.kr)
        self.assertLess(after, before + 2,
                        "без признака строки файла подставляться не должны")


class AcpuPrint(unittest.TestCase):
    """Печать на АЦПУ — отдельным сеансом и последней в файле.

    Задача печати выводит не только файл, но и подвал с регистрами
    (`КОНЕЦ ЗАДАЧИ`, `ОТЧЁТ`), поэтому машина занята печатью минутами и
    последующие вводы `ДОП` не успевают за окнами ожидания. Проверка
    вынесена так, чтобы не мешать остальным.
    """

    @classmethod
    def setUpClass(cls):
        cls.kr = KrabSession()
        cls.kr.login_or_skip()
        cls.kr.cleanup()

    @classmethod
    def tearDownClass(cls):
        cls.kr.cleanup()
        cls.kr.close()

    def test_01_pechat_pn(self):
        """`АЦП ПН` печатает файл: растёт файл центрального АЦПУ.

        Требует, чтобы АЦПУ был подключён оператором (`ДАЙ А0`) — иначе
        задача ставится в очередь, а файл не растёт.
        """
        _make(self.kr, ("январь", "февраль"))
        before = _size(ACPU)
        out = self.kr.directive("ацп пн", timeout=90)
        for _ in range(6):                 # печать идёт порциями
            time.sleep(5)
            if _size(ACPU) > before:
                break
        after = _size(ACPU)
        if after > before:
            self.assertGreater(after, before)
        else:
            self.assertTrue(any(x in out for x in DENIED),
                            f"печати нет, но и отказа не видно: {out!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
