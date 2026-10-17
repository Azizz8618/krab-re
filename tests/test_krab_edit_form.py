"""Редактирование, формирование задач и просмотр результата (ЛИСТ).

Пользователь 1234 / ключ 1234, терминал 15ИЭ-00-013. Протокол снят с живой
машины (ВЕР.19 ОТ 27.11.92):

    имя нф   ->  ИМЯ НФ / НЕТ В КАТАЛОГЕ / -      (файл не найден, образован)
    доп      ->  приглашение «+», строки эхом, пустая посылка — конец
    дли      ->  NNNN  NNНН  NNНН   (карт, слов, УК)
    выд 1-2  ->  0001 ТЕКСТ / 0002 ТЕКСТ
    упл      ->  уплотнение, длина меняется
    ред 1-99 ->  ЛИБО «НЕТ ИМЕНИ МАССИВА», ЛИБО приглашение «/»
    зап      ->  приглашение «ПАРОЛЬ», пустая посылка → отказ
    фор      ->  ОШИБКА В ПАСПОРТЕ (текущего файла нет в архиве)
    лис      ->  (быстрый тест только проверяет отказ без задачи)

Быстрые тесты по умолчанию; полный прогон FormationLive (реальное
формирование и просмотр листинга) включается KRAB_LIVE_FORM=1 — он считать
может и минуту, поэтому в штатные прогоны не ставится.

Запуск: python3 -m pytest tests/test_krab_edit_form.py -v
"""
from __future__ import annotations

import os
import unittest

from krab_session import KEY, USER, KrabSession, fold


def live_form() -> bool:
    return os.environ.get("KRAB_LIVE_FORM") == "1"


class EditTextFile(unittest.TestCase):
    """Один вход на класс, короткие ожидания (1–3 с)."""

    @classmethod
    def setUpClass(cls):
        cls.kr = KrabSession()
        cls.kr.login()

    @classmethod
    def tearDownClass(cls):
        cls.kr.close()

    def _new_file(self):
        """Образовать пустой текущий файл и наполнить тремя строками ДОП.

        ДОП работает как построчный ввод: система спрашивает «+» и ждёт
        следующую строку, пока не придёт пустая. Поэтому каждая строка —
        отдельный вызов directive(), ожидающий приглашения.
        """
        self.kr.directive("имя бтскр")
        out = self.kr.directive("доп")
        self.assertIn("+", out, f"нет приглашения ДОП: {out!r}")
        for t in ("январь", "февраль", "март"):
            self.kr.directive(t, timeout=20)
        self.kr.directive("", timeout=20)                # пустая — конец ввода

    def test_01_imya_novogo_fayla(self):
        """ИМЯ файла, которого нет в архиве.

        Ответ бывает двух видов: «НЕТ В КАТАЛОГЕ», если файла нет нигде, и
        «ФАЙЛ СО СБОЙНЫХ ЗОН», если он остался на рабочих зонах от прошлого
        прогона (файл рабочего поля не из архива). Оба означают, что файл
        из архива не поднят.
        """
        out = self.kr.directive("имя бтскр")
        self.assertIn("ИМЯ БТСКР", out)
        self.assertTrue("НЕТ В КАТАЛОГЕ" in out or "СО СБОЙНЫХ ЗОН" in out,
                        f"неожиданный ответ ИМЯ: {out!r}")

    def test_02_dop_napolnenie(self):
        """ДОП наполняет файл; длина подтверждает три строки."""
        self._new_file()
        out = self.kr.directive("дли")
        self.assertIn("0003", out)               # три карты

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
        out = self.kr.directive("дли")
        self.assertIn("0003", out)

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
            kr.login()
            out = kr.directive("ред 1-999")
            self.assertIn("НЕТ ИМЕНИ МАССИВА", out)

    def test_07_zap_trebuet_parol(self):
        """ЗАП запрашивает ПАРОЛЬ; голая посылка даёт отказ гостя."""
        self._new_file()
        out = self.kr.send("зап бтскр", 2.0, 30)
        self.assertIn("ПАРОЛЬ", out)
        out2 = self.kr.send("", 3.0, 30)         # пароль не задан
        self.assertIn("НЕТ МЕСТА В АРХИВЕ", out2)

    def test_08_for_trait_novogo_fayla(self):
        """ФОР несохранённого файла: ОШИБКА В ПАСПОРТЕ."""
        self._new_file()
        out = self.kr.directive("фор", quiet=3.0, timeout=60)
        self.assertIn("ФОР", out)
        self.assertIn("ОШИБКА В ПАСПОРТЕ", out)

    def test_09_lis_bez_zadachi(self):
        """ЛИС без ПЗ быстро отвечает отказом/состоянием, не виснет."""
        out = self.kr.directive("лис", quiet=2.0, timeout=45)
        self.assertTrue(fold(out), "нет ответа на ЛИС")

    def test_10_vse_diagnostiki_posl_i_slov(self):
        """Строка из файла сохраняется дословно: эхо ДОП = содержимое."""
        self._new_file()
        out = self.kr.directive("выд 3-3")
        self.assertIn("0003 МАРТ", out)


@unittest.skipUnless(live_form(), "полный прогон ФОР→ЛИС: включается "
                                  "KRAB_LIVE_FORM=1, считать может минуту")
class FormationLive(unittest.TestCase):
    """Реальное формирование и просмотр листинга (медленный путь)."""

    @classmethod
    def setUpClass(cls):
        cls.kr = KrabSession()
        cls.kr.login()

    @classmethod
    def tearDownClass(cls):
        cls.kr.close()

    def test_form_and_list(self):
        """ФОР по сохранённому файлу + ЛИС: проверка реакции, не листинга."""
        self.kr.directive("имя бтскр")
        self.kr.send("фор пак", 3.0, 90)
        # успех — что-то про задачу/номер; иначе отказFormation
        out = self.kr.directive("лис", quiet=5.0, timeout=180)
        self.assertTrue(fold(out))


if __name__ == "__main__":
    unittest.main(verbosity=2)
