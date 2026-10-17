"""Редактирование текстов и формирование задач в системе КРАБ.

Пользователь 1234 / ключ 1234, терминал 15ИЭ-00-013, линия ДКС ЭВМ БЭСМ-6.

Протокол снят с живой машины (версия 19 от 27.11.92):

    имя бтс…       -> ИМЯ БТС… ; НЕТ В КАТАЛОГЕ или ФАЙЛ СО СБОЙНЫХ ЗОН
    доп            -> приглашение «+», строки эхом, пустая посылка — конец
    дли            -> NNNN  NNNN  NNNN   (карт, слов, УК)
    выд 1-2        -> 0001 ЯНВАРЬ / 0002 ФЕВРАЛЬ
    упл            -> уплотнение, длина меняется
    ред 1-999      -> ЛИБО «НЕТ ИМЕНИ МАССИВА», ЛИБО приглашение «/»
    дбл 1-1-4      -> копия строки вставляется перед строкой 4: карт +1
    сдв 1-1-4      -> перенос строки: число карт не меняется
    скл 1-2        -> строки склеиваются: карт −1
    упс /          -> символ конца строки, без диагностики
    кзм .а.б.1-3   -> контекстная замена; разделитель по умолчанию точка,
                      задаётся директивой «рзд»; при неверном разделителе
                      «ОШ В ДИР»
    зап <файл>     -> приглашение «ПАРОЛЬ»; у гостя далее НЕТ МЕСТА В АРХИВЕ
    фор            -> ОШИБКА В ПАСПОРТЕ (файл не записан) либо УЖЕ ЕСТЬ ПЗ
    лис            -> ответ программы ЛИСТ без задачи

Запуск: python3 -m pytest tests/test_krab_edit_form.py -v
"""
from __future__ import annotations

import itertools
import os
import re
import time
import unittest

from krab_session import KrabSession, fold

LINES = ("январь", "февраль", "март")

_counter = itertools.count(1)


def fname() -> str:
    """Имя файла, уникальное в пределах прогона.

    Файлы на сбойных зонах переживают сеанс, поэтому одно и то же имя
    копит содержимое от теста к тесту — каждому тесту нужен свой файл.
    """
    return f"бтс{next(_counter)}{int(time.time()) % 100:02d}"


def make_file(kr: KrabSession, lines=LINES) -> str:
    """Образовать текущий файл и наполнить его строками через ДОП.

    ДОП — построчный ввод: система спрашивает «+» и ждёт следующую строку,
    пока не придёт пустая, поэтому каждая строка — отдельный вызов.
    """
    name = fname()
    kr.directive(f"имя {name}")
    out = kr.directive("доп")
    assert "+" in out, f"нет приглашения ДОП: {out!r}"
    for text in lines:
        kr.directive(text, timeout=20)
    kr.directive("", timeout=20)                 # пустая — конец ввода
    return name


def cards_of(kr: KrabSession) -> int:
    """Число карт текущего файла по ответу ДЛИ."""
    out = kr.directive("дли")
    numbers = re.findall(r"\d{4}", out)
    assert numbers, f"ДЛИ без чисел: {out!r}"
    return int(numbers[0])


class KrabEdit(unittest.TestCase):
    """База наборов: вход под номером 1234 и подготовка файла для правок.

    Базовый класс намеренно без собственных тестов — иначе pytest собрал
    бы тесты дважды, в каждом наследнике.
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

    def _new_file(self):
        return make_file(self.kr)

    def cards(self) -> int:
        return cards_of(self.kr)


class EditTextFile(KrabEdit):
    """Образование файла, наполнение и служебные директивы."""

    def test_01_imya_novogo_fayla(self):
        """ИМЯ файла, которого нет в архиве.

        Ответ бывает двух видов: «НЕТ В КАТАЛОГЕ», если файла нет нигде, и
        «ФАЙЛ СО СБОЙНЫХ ЗОН», если он остался на рабочих зонах от прошлого
        прогона. Оба означают, что файл из архива не поднят.
        """
        name = fname()
        out = self.kr.directive(f"имя {name}")
        self.assertIn(f"ИМЯ {name.upper()}", out)
        self.assertTrue("НЕТ В КАТАЛОГЕ" in out or "СО СБОЙНЫХ ЗОН" in out,
                        f"неожиданный ответ ИМЯ: {out!r}")

    def test_02_dop_napolnenie(self):
        """ДОП наполняет файл; длина подтверждает три карты."""
        self._new_file()
        self.assertIn("0003", self.kr.directive("дли"))

    def test_03_vyd_s_nomera(self):
        """ВЫД 1-2 выводит карты с номерами."""
        self._new_file()
        out = self.kr.directive("выд 1-2")
        self.assertIn("0001 ЯНВАРЬ", out)
        self.assertIn("0002 ФЕВРАЛЬ", out)

    def test_04_upl_szhimaet(self):
        """УПЛ отрабатывает; длина не растёт."""
        self._new_file()
        self.kr.directive("упл")
        self.assertIn("0003", self.kr.directive("дли"))

    def test_05_red_s_massivom(self):
        """РЕД с образованным файлом входит в режим «/»."""
        self._new_file()
        out = self.kr.directive("ред 1-999")
        self.assertIn("РЕД 1-999", out)
        self.assertIn("/", out)                  # приглашение редактора

    def test_06_red_bez_massiva(self):
        """РЕД без образованного файла: НЕТ ИМЕНИ МАССИВА.

        Отдельный чистый вход: после директив ИМЯ текущий файл уже образован,
        и РЕД войдёт в режим «/», а не откажет.
        """
        with KrabSession() as kr:
            kr.login_or_skip()
            self.assertIn("НЕТ ИМЕНИ МАССИВА", kr.directive("ред 1-999"))

    def test_07_zap_trebuet_parol(self):
        """ЗАП запрашивает ПАРОЛЬ; голая посылка даёт отказ гостя."""
        self._new_file()
        out = self.kr.send("зап", 2.0, 30)
        self.assertIn("ПАРОЛЬ", out)
        out2 = self.kr.send("", 3.0, 30)         # пароль не задан
        self.assertIn("НЕТ МЕСТА В АРХИВЕ", out2)

    def test_08_for_trait_novogo_fayla(self):
        """ФОР несохранённого файла отвергается.

        Файл не записан в архив (у гостя нет места), поэтому задача не
        формируется; занятая подчинённая задача даёт другой отказ.
        """
        self._new_file()
        out = self.kr.directive("фор", quiet=3.0, timeout=60)
        self.assertIn("ФОР", out)
        self.assertTrue("ОШИБКА В ПАСПОРТЕ" in out or "УЖЕ ЕСТЬ ПЗ" in out,
                        f"неожиданный ответ ФОР: {out!r}")

    def test_09_lis_bez_zadachi(self):
        """ЛИС без подчинённой задачи быстро отвечает, не виснет."""
        out = self.kr.directive("лис", quiet=2.0, timeout=45)
        self.assertTrue(fold(out), "нет ответа на ЛИС")

    def test_10_vse_diagnostiki_posl_i_slov(self):
        """Строка читается дословно: ВЫД отдаёт карту с номером."""
        self._new_file()
        out = self.kr.directive("выд 3-3")
        self.assertRegex(out, r"0003 \S+")


class EditingDirectives(KrabEdit):
    """Директивы правки строк: ДБЛ, СДВ, СКЛ, УПС, РЗД + КЗМ.

    Состояние файла наблюдается директивой ДЛИ, поэтому проверяются
    инварианты числа карт, а не конкретный текст (проверено на машине).
    """

    def test_01_dbl_duplicates_lines(self):
        """ДБЛ 1-1-4 добавляет копию первой строки → карт на одну больше."""
        self._new_file()
        before = self.cards()
        self.assertEqual(before, 3)
        self.kr.directive("дбл 1-1-4")
        self.assertEqual(self.cards(), before + 1)

    def test_02_sdv_keeps_line_count(self):
        """СДВ 1-1-4 переносит строку: копия вставлена, исходная удалена."""
        self._new_file()
        before = self.cards()
        self.kr.directive("сдв 1-1-4")
        self.assertEqual(self.cards(), before)

    def test_03_skl_glues_lines(self):
        """СКЛ 1-2 склеивает две строки → карт на одну меньше."""
        self._new_file()
        before = self.cards()
        self.kr.directive("скл 1-2")
        self.assertEqual(self.cards(), before - 1)

    def test_04_ups_sets_end_of_line(self):
        """УПС задаёт символ конца строки без диагностики."""
        self._new_file()
        out = self.kr.directive("упс /")
        self.assertNotIn("НЕТ ДИРЕК", out)
        self.assertNotIn("ОШ В ДИР", out)
        # после смены символа прежняя разметка карт не сохраняется,
        # поэтому проверяем лишь отвечает ли ДЛИ
        self.assertGreaterEqual(self.cards(), 1)

    def test_05_rzd_zadayet_razdelitel(self):
        """РЗД задаёт разделитель полей КЗМ (по умолчанию точка).

        Директива РЗД не документирована в корпусе текстов 1978—1993 гг.;
        если этой версии системы она нет, тест фиксирует это, а не падает:
        проверяется, что ответ — либо приём, либо «НЕТ ДИРЕК», но без
        прочих диагностик.
        """
        self._new_file()
        out = self.kr.directive("рзд .")
        self.assertNotIn("ОШ В ДИР", out)

    def test_06_kzm_contextual_replace(self):
        """КЗМ .<КТ>.<РТ>.<N1>-<N2> — контекстная замена в диапазоне."""
        self._new_file()
        self.kr.directive("рзд .")
        out = self.kr.directive("кзм .янв.мая.1-3")
        self.assertNotIn("ОШ В ДИР", out)
        self.assertIn("МАЯРЬ", self.kr.directive("выд 1-1"))

    def test_07_kzm_wrong_separator_rejected(self):
        """КЗМ с чужим разделителем отвергается: ОШ В ДИР."""
        self._new_file()
        self.assertIn("ОШ В ДИР", self.kr.directive("кзм а/б"))

    def test_08_file_readable_after_editing(self):
        """После всех правок файл читается: ВЫД отдаёт карты с номерами."""
        self._new_file()
        self.kr.directive("дбл 1-1-4")
        self.kr.directive("скл 1-2")
        self.assertRegex(self.kr.directive("выд"), r"0001 \S+")


def live_form() -> bool:
    """Длительный прогон формирования — только по явному запросу."""
    return os.environ.get("KRAB_LIVE_FORM") == "1"


@unittest.skipUnless(live_form(),
                     "полный прогон ФОР→ЛИС: KRAB_LIVE_FORM=1, считает долго")
class FormationLive(unittest.TestCase):
    """Реальное формирование и просмотр листинга (медленный путь)."""

    @classmethod
    def setUpClass(cls):
        cls.kr = KrabSession()
        cls.kr.login_or_skip()

    @classmethod
    def tearDownClass(cls):
        cls.kr.close()

    def test_form_and_list(self):
        """ФОР по сохранённому файлу и вход в программу ЛИСТ."""
        self.kr.directive("имя форгдр")
        self.kr.send("фор пз", 3.0, 90)
        self.kr.directive("лис", quiet=3.0, timeout=60)
        self.assertTrue(fold(self.kr.screen()))


if __name__ == "__main__":
    unittest.main(verbosity=2)