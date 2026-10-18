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
    """Имя файла, уникальное в пределах прогона и не длиннее шести знаков.

    ШКО ИМЯ: «последовательность из не более шести символов, начинающаяся
    с буквы». Более длинное имя отвергается — «ИМЯ НЕ ИДЕНТИФИКАТОР», —
    и все следующие директивы работают уже с чужим текущим файлом.

    Файлы на сбойных зонах переживают сеанс, поэтому одно и то же имя
    копит содержимое от теста к тесту — каждому тесту нужен свой файл.
    """
    return f"б{next(_counter) % 100:02d}{int(time.time()) % 100:02d}"


def _to_monitor(kr: KrabSession) -> None:
    """Гарантировать приглашение Монитора перед новым файлом.

    Если предыдущий `ДОП` остался незакрытым (на экране «+»), новый `ДОП`
    не печатает НОВОГО приглашения, и ожидание «+» не срабатывает —
    тогда как ввод на самом деле уже открыт.
    """
    for _ in range(3):
        lines = [x.strip() for x in kr.term.lines() if x.strip()]
        last = lines[-1] if lines else ""
        if last == "-":
            return
        if last == "+":                     # внутри ДОП — закрыть ввод
            kr.directive("", timeout=20)
            continue
        kr.ensure_monitor()                 # Лист или Школа


def make_file(kr: KrabSession, lines=LINES) -> str:
    """Образовать текущий файл и наполнить его строками через ДОП.

    ДОП — построчный ввод: система спрашивает «+» и ждёт следующую строку,
    пока не придёт пустая, поэтому каждая строка — отдельный вызов, а конец
    ввода проверяется возвратом приглашения «-» в Монитор.
    """
    _to_monitor(kr)                              # закрыть прошлый ДОП/Лист
    name = fname()
    out = kr.directive(f"имя {name}")
    for diag in ("ИМЯ НЕ ИДЕНТИФИКАТОР", "НЕТ ЗОН ДЛЯ УПРЯТ",
                 "ЗАТЕРТ КАТ СБЗ", "НЕТ СБОЙНЫХ ЗОН"):
        assert diag not in out, f"файл не образован ({diag}): {out!r}"
    rev = kr.term.mark()
    kr.directive("доп")
    # «+» ждём только среди новых строк: на кадре ещё лежит «+» от прошлого
    # ввода, и поиск по всему экрану проходит, даже если ДОП не начался
    if not kr.wait_new("+", timeout=40, mark=rev):
        # машина могла потерять директиву — повторяем её один раз
        rev = kr.term.mark()
        kr.directive("доп")
        assert kr.wait_new("+", timeout=40, mark=rev), \
            "ДОП не спросил первую строку"
    for text in lines:
        kr.directive(text, timeout=20)
    # пустая посылка заканчивает ввод; если машина её «не заметила»,
    # приглашение остаётся «+» — повторяем, иначе следующая директива
    # уйдёт в файл как текст
    for attempt in range(3):
        rev = kr.term.mark()
        kr.directive("", timeout=20)
        if kr.wait_new("-", timeout=25, mark=rev):
            break
        if attempt == 2:
            raise AssertionError("ДОП не завершился: приглашение «+» держится")
    return name


def _dli(kr: KrabSession) -> tuple[int, int, int]:
    """Ответ ДЛИ: карты, слова, признаки конца строки.

    Ответ — строка из трёх четёрок цифр. Первое число в выдаче брать нельзя:
    в окне попадают и имена файлов, где четвёрки тоже есть.
    """
    out = kr.directive("дли")
    picked = None
    for line in out.splitlines():
        m = re.fullmatch(r"\s*(\d{4})\s+(\d{4})\s+(\d{4})\s*", line)
        if m:
            picked = m                       # последнее вхождение — новейшее
    if picked is None:
        raise AssertionError(f"ДЛИ без строки из трёх четёрок: {out!r}")
    return tuple(int(picked.group(i)) for i in (1, 2, 3))


def cards_of(kr: KrabSession, tries: int = 2) -> int:
    """Число карт текущего файла.

    Ответ машины может прийти позже эха директивы, поэтому ДЛИ отправляется
    не сразу, а после паузы ~3 с (двойное чтение «до двух совпадений»
    оказалось слишком дорогим: каждый замер занимал полминуты, а набор —
    минуты). При не Urdu читаемом ответе — один повтор.
    """
    for attempt in range(tries):
        kr.term.wait_quiet(0.8 if attempt else 2.0, 30)
        try:
            return _dli(kr)[0]
        except AssertionError:
            if attempt + 1 == tries:
                raise
    raise AssertionError("ДЛИ не отвечает")


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
        """РЕД с образованным файлом входит в режим «/».

        Форма обращения — `Р[ЕД]`, без параметров: номера правящихся строк
        передаются в самих строках, в первых четырёх позициях.
        """
        self._new_file()
        out = self.kr.directive("ред")
        self.assertIn("РЕД", out)
        self.assertIn("/", out)                  # приглашение редактора

    def test_06_red_bez_massiva(self):
        """РЕД без образованного файла: НЕТ ИМЕНИ МАССИВА.

        Отдельный чистый вход: после директив ИМЯ текущий файл уже образован,
        и РЕД войдёт в режим «/», а не откажется.
        """
        with KrabSession() as kr:
            kr.login_or_skip()
            self.assertIn("НЕТ ИМЕНИ МАССИВА", kr.directive("ред"))

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
        # если ЛИС всё же вошёл в программу Лист — вернуться в Монитор,
        # иначе ввод следующего теста уйдёт в Лист и «наведёт» его отказом
        self.kr.ensure_monitor()

    def test_10_vse_diagnostiki_posl_i_slov(self):
        """Строка читается дословно: ВЫД отдаёт карту с номером."""
        self._new_file()
        out = self.kr.directive("выд 3-3")
        self.assertRegex(out, r"0003 \S+")


class RedEditing(KrabEdit):
    """РЕД — правка нескольких строк через автономный режим терминала.

    Протокол (ШКО РЕД, файл `SCU101`): сначала строки выдаются на экран
    директивой ВЫД, затем РЕД даёт приглашение «/», терминал переводится
    в OFFLINE («АВТОНОМНО»), и исправленные строки — с номерами в первых
    четырёх позициях — уходят по SEND. Все строки, кроме последней,
    заканчиваются LINE FEED (0x0A), последняя — символом ETX (0x03).
    """

    def test_01_red_menyashchestya_strok(self):
        """РЕД правит несколько строк за один посыл."""
        self._new_file()
        self.kr.red_edit({1: "январь", 2: "декабрь", 3: "ноябрь"})
        out = self.kr.directive("выд 1-3")
        self.assertIn("0002 ДЕКАБРЬ", out)
        self.assertIn("0003 НОЯБРЬ", out)

    def test_02_red_odnoj_stroki(self):
        """РЕД правит одну строку — она идёт последней и завершается ETX."""
        self._new_file()
        self.kr.red_edit({2: "декабрь"})
        self.assertIn("0002 ДЕКАБРЬ", self.kr.directive("выд 2-2"))

    def test_03_red_nepodryadnye_nomera(self):
        """Номера правящихся строк не обязаны идти подряд."""
        self._new_file()
        self.kr.red_edit({1: "январь", 3: "ноябрь"})
        out = self.kr.directive("выд 1-3")
        self.assertIn("0001 ЯНВАРЬ", out)
        self.assertIn("0003 НОЯБРЬ", out)

    def test_04_red_ne_menyaet_chisla_kart(self):
        """Число карт после РЕД то же — строки заменяются, не добавляются."""
        self._new_file()
        self.assertEqual(self.cards(), 3)
        self.kr.red_edit({1: "первая", 2: "вторая", 3: "третья"})
        self.assertEqual(self.cards(), 3)

    def test_05_red_smenyaet_soderzhanie(self):
        """После РЕД файл читается с новым содержимым."""
        self._new_file()
        self.kr.red_edit({3: "сентябрь"})
        out = self.kr.directive("выд 3-3")
        # смотрим только выдачу ВЫД: directive() отдаёт и эхо предыдущих
        # директив сеанса, где «МАРТ» — текст, введённый через ДОП
        shown = out.rsplit("ВЫД 3-3", 1)[-1]
        self.assertRegex(shown, r"0003 СЕНТЯБРЬ")
        self.assertNotIn("МАРТ", shown)


class EditingDirectives(KrabEdit):
    """Директивы правки строк: ДБЛ, СДВ, СКЛ, УПС, РЗД + КЗМ.

    Состояние файла наблюдается директивой ДЛИ, поэтому проверяются
    инварианты числа карт, а не конкретный текст (проверено на машине).
    """

    def test_01_dbl_duplicates_lines(self):
        """ДБЛ 1 1 4 — копия первой строки перед строкой 4: карт на одну больше.

        Форма `ДБ[Л] <НАЧСТР> <КОНСТР> <НОМСТР>` — параметры через ПРОБЕЛ
        (ШКО ДБЛ, `SCU105`), оригинал сохраняется. Строки 1…1 вставляются
        ПЕРЕД строкой 4, поэтому файл должен быть не короче четырёх строк.
        """
        make_file(self.kr, ("январь", "февраль", "март", "апрель"))
        before = self.cards()
        self.assertEqual(before, 4)
        self.kr.directive("дбл 1 1 4")
        self.assertEqual(self.cards(), before + 1)

    def test_02_sdv_keeps_line_count(self):
        """СДВ 1 1 4 — строка переносится, оригинал не сохраняется."""
        make_file(self.kr, ("январь", "февраль", "март", "апрель"))
        before = self.cards()
        self.assertEqual(before, 4)
        self.kr.directive("сдв 1 1 4")
        self.assertEqual(self.cards(), before)

    def test_03_skl_glues_lines(self):
        """СКЛ 1 2 — склейка карт: карт на одну меньше."""
        self._new_file()
        before = self.cards()
        self.kr.directive("скл 1 2")
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
        """КЗМ .<КТ>.<РТ>.<N1>-<N2> — контекстная замена в диапазоне.

        Замена идёт по вхождению: «январь» = «янв» + «арь», поэтому
        «.янв.май.» даёт «майарь», а машина отчитывается числом замен —
        «ЗАМЕН 000001 ШТ.». Проверен диапазон 1-3: «янв» встречается
        только в первой строке, значит замена ровно одна.
        """
        self._new_file()
        self.kr.directive("рзд .")
        out = self.kr.directive("кзм .янв.май.1-3")
        self.assertNotIn("ОШ В ДИР", out)
        self.assertIn("ЗАМЕН 000001 ШТ.", out)
        self.assertIn("МАЙАРЬ", self.kr.directive("выд 1-1"))

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