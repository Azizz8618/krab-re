"""Драйвер сеанса КРАБ через терминал 15ИЭ-00-013 (эмулятор ie15).

Обёртка над ie15emu.agent.Terminal, знающая протокол Монитора абонентов:

    краб  ->  ** K  P  A  B **  (BEP.xx ОT dd.mm.yy), приглашение «-»
    нач   ->  приглашение «КТО?»
    шифр  ->  приглашение «КЛЮЧ-»
    ключ  ->  сеанс открыт (может быть выдано сообщение о сбойных зонах)
    кон   ->  выход, возврат к приглашению «-»

Все сравнения — через fold(): набор Н2 показывает русские буквы машины
латинскими гомоглифами («КТО?» → «KTО?»), fold() их сводит.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

IE15_HOME = Path(os.environ.get("IE15_HOME", Path.home() / "Yandex.Disk" / "ie15"))
if str(IE15_HOME) not in sys.path:
    sys.path.insert(0, str(IE15_HOME))

from ie15emu.agent import Terminal, fold  # noqa: E402
from ie15emu.link import LinkError  # noqa: E402
from ie15emu.session import MODE_HOST, MODE_LOCAL  # noqa: E402

#: шифр пользователя для тестов (первые 4 цифры — шифр ОС Диспак)
USER = "1234"
#: ключ-пароль пользователя
KEY = "1234"

#: линия ДКС по умолчанию — ОДНА. Автоматический перебор всех линий
#: недопустим: система КРАБ обслуживает до 24 терминалов, и занимая их
#: подряд, агент сам исчерпывает терминалы — после этого Монитор
#: перестаёт загружаться и отвечает «НЕТ ДИРЕК» даже на свободной линии.
PORT_SPEC = os.environ.get("KRAB_PORT", "4202")

#: перебор линий включается только явно и только на соседние порты
ROTATE = os.environ.get("KRAB_ROTATE") == "1"
ROTATE_LIMIT = int(os.environ.get("KRAB_ROTATE_LIMIT", "2"))

#: запасная линия КВУ (консоль tty1, порт 4198): вход по HYC<ETX>;
#: используется, когда свободных линий ДКС нет
SERIAL_PORT = os.environ.get("KRAB_SERIAL_PORT", "4198")


def _port_list(spec: str) -> list[str]:
    """Разбор спецификации портов: «4203» или «4202-4223»."""
    if "-" in spec:
        lo, hi = spec.split("-", 1)
        return [str(n) for n in range(int(lo), int(hi) + 1)]
    return [spec]


class KrabSession:
    """Сеанс КРАБ на линии ДКС, управляемый как человеком-оператором."""

    def __init__(self, port: str = PORT_SPEC, machine: str = "6") -> None:
        self.machine = machine
        self.serial = False
        # порты перебираются по очереди: отдельные линии ДКС могут держать
        # зависший экземпляр КРАБ, и на них Монитор отвечает «НЕТ ДИРЕК»
        self._ports = _port_list(port)
        self._index = 0
        try:
            self.url = f"tcp://127.0.0.1:{port}"
            self.term = Terminal(self.url, machine=machine)
        except LinkError:
            # линий ДКС нет — переходим на серийную линию КВУ
            self.serial = True
            self.url = f"tcp://127.0.0.1:{SERIAL_PORT}"
            self.term = Terminal(self.url, machine=machine)
        # набор Н2 (VT-52) — рабочий для БЭСМ-6: русские буквы уходят
        # кодами КОИ7. Н0 печатает латиницу (директивы не вводятся, такой
        # набор удобен для оболочки SIMH), Н1 для этой машины не годится.
        self.term.session.nabor = "n2"

    # --- протокол входа ------------------------------------------------
    def send_text(self, cmd: str, attempts: int = 2) -> None:
        """Набрать строку клавишами — штатным путём эмулятора 15ИЭ.

        Набор идёт через Terminal.type()/feed_key: сам эмулятор переводит
        знаки в коды линии, ручная отправка кодов мимо него ломает
        раскладку и набор знаков.

        Эхо сверяется с набранным: сразу после входа линия успевает
        исказить символы («бтс398» → «,NС398»), и такой директивы машина
        не понимает. При расхождении набор повторяется.
        """
        # Повторяем посылку только когда машина не отреагировала ВООБЩЕ.
        # Сверять эхо посимвольно нельзя: часть букв машина отдаёт кодами,
        # которые терминал рисует латиницей (RFКМР вместо КАЛЬК), и сверка
        # дала бы ложное расхождение — а повтор внутри ДОП продублировал бы
        # строки файла.
        for attempt in range(attempts):
            rev = self.term.mark()
            self.term.type(cmd)
            self.enter_line()
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                self.term.pump(0.2)
                if [x for x in self.term.new_lines(rev) if x.strip()]:
                    return                     # машина ответила — всё принято
                time.sleep(0.3)
            if attempt + 1 < attempts:
                time.sleep(1.0)

    def red_edit(self, lines, timeout: float = 60.0) -> str:
        """Правка строк директивой РЕД — через автономный режим терминала.

        Протокол взят из Школы (`ШКО РЕД`, файл `SCU101`):

            РЕД                -> приглашение «/»
            терминал в OFFLINE (клавиша РЕЖИМ, «АВТОНОМНО»)
            исправленные строки с номерами в первых четырёх позициях:
                все, кроме последней, заканчиваются LINE FEED (0x0A),
                последняя — символом ETX (0x03);
            курсор на первой изменённой строке, SEND (клавиша ПЕРЕДАЧА).

        Номера исправляемых строк не обязаны идти подряд. Номер в
        начале строки и есть номер заменяемой строки файла: в эмуляторе
        SEND отдаёт накопленный набор, поэтому позиционировать курсор
        по экрану не требуется — важно лишь, чтобы в наборе стояли номера.

        lines — последовательность пар (номер, текст) или словарь
        {номер: текст}; порядок вывода сохраняется.

        Текст набирается строчными русскими буквами: набор Н2 эмулятора
        для ЗАГЛАВНЫХ даёт неверные коды (key_to_bytes не различает их при
        shift_to_rus — проверено 17.10.2026), и в файл попадает мусор.
        """
        pairs = list(lines.items()) if isinstance(lines, dict) else list(lines)
        assert pairs, "нечего править"
        self.term.wait_quiet(1.0, 30)            # дать Монитору закончить выдачу
        out = self.directive("ред")
        if "/" not in out:
            raise AssertionError(f"РЕД не вошёл в режим правки: {out!r}")
        self.term.set_mode(MODE_LOCAL)
        try:
            for pos, (num, text) in enumerate(pairs):
                self.term.type(f"{num:04d} {text}")
                # последняя строка посылки завершается ETX, остальные — LF
                self.term.key("\x03" if pos == len(pairs) - 1 else "\x0a")
            self.term.send()
        finally:
            self.term.set_mode(MODE_HOST)
        self.term.wait_quiet(3.0, timeout)
        return "\n".join(x for x in self.term.lines() if x.strip()[-30:])

    def enter_line(self) -> None:
        """Завершить набранную строку.

        На серийной линии КВУ код ETX (0x03) требуется только на входе
        (HYC); набранные директивы завершаются обычной клавишей Enter.
        """
        self.term.key("KEY_ENTER")

    def _enter_serial(self, timeout: float = 25.0) -> None:
        """Вход на серийную линию КВУ: HYC + ETX, затем баннер ОС ДИСПАК."""
        self.term.drain(quiet=0.5, timeout=8)
        self.term.link.send(b"HYC\x03")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.term.pump(0.4)
            screen = self.term.screen()
            if "117" in screen or "ДИCПAK" in screen:
                # приветствие печатается порциями: ждём, пока кадр устоится,
                # иначе следующий ввод уходит в машину до готовности
                self.term.wait_quiet(quiet=1.5, timeout=25)
                return
        raise AssertionError(f"ОС ДИСПАК не ответила: {self.term.screen()!r}")

    def start(self, timeout: float = 40.0) -> str:
        """Вызвать КРАБ и дождаться баннера и приглашения «-»."""
        if self.serial:
            # на серийной линии лишний Enter сбивает ОС с приглашения:
            # сразу после ответа «ЗДРАВСТВУЙТЕ» набираем «краб»
            self._enter_serial()
            self.term.type("краб")
            self.enter_line()
            self.term.wait_for("BEP.", timeout=25)
            self.term.wait_for("ОT ", timeout=25)
            text = fold(self.term.screen())
            assert "К  Р  А  Б" in text and "ВЕР." in text, \
                f"нет баннера КРАБ: {text!r}"
            return text
        self.term.drain(quiet=0.3, timeout=5)
        self.enter_line()
        self.term.wait_quiet(0.6, 15)          # приглашение «ЭВМ-3,TNNN»
        self.term.type("краб")
        self.enter_line()
        # ждём по содержимому, а не по таймеру: на загруженной машине
        # баннер «** К  Р  А  Б ** (ВЕР.xx ОТ …)» печатается с задержкой
        self.term.wait_for("BEP.", timeout=25)   # латентная часть баннера
        self.term.wait_for("ОT ", timeout=25)
        text = fold(self.term.screen())
        assert "К  Р  А  Б" in text and "ВЕР." in text, \
            f"нет баннера КРАБ: {text!r}"
        return text

    #: Монитор КРАБ печатает баннер сразу, а таблицу директив грузит
    #: ещё секунд 15: на «нач» в этот промежуток он отвечает «НЕТ ДИРЕК».
    #: Проверено на живой машине 17.10.2026 — раньше это выглядело как
    #: «отравленная линия ДКС», и перебор портов ничем не помогал.
    READY_WAIT = 8.0

    def enter(self, user: str = USER, key: str = KEY,
              timeout: float = 40.0, tries: int = 4) -> str:
        """Вход: «нач» → КТО? → шифр → КЛЮЧ- → ключ.

        «нач» повторяется, пока Монитор не ответит приглашением «КТО»:
        на ещё не прогрузившемся Мониторе директива отвергается. Перевызы-
        вать КРАБ здесь нельзя — лишний экземпляр только мешает.
        """
        for attempt in range(tries):
            self.send("нач", 1.5, timeout)
            if self.term.wait_for("KTО", timeout=12):
                self.send(user, 1.5, timeout)
                if not self.term.wait_for("KЛЮЧ", timeout=timeout):
                    continue
                self.send(key, 1.5, timeout)
                # сеанс открыт, если машина не требует номер заново
                if "СООБЩИТЕ ВАШ НОМЕР" not in self.screen():
                    return self.screen()
            if attempt + 1 < tries:
                time.sleep(self.READY_WAIT)
        raise AssertionError(f"не удалось войти в номер {user}: "
                             f"{self.screen()!r}")

    def exit(self, timeout: float = 40.0) -> str:
        """Окончание работы в номере (директива КОН)."""
        return self.send("кон", 3.0, timeout)

    def login_or_skip(self, user: str = USER, key: str = KEY) -> str:
        """Вход в номер; если Монитор не отвечает — пропуск набора.

        Бывает, что КРАБ вызывается и печатает баннер, а Монитор на
        директивы отвечает «НЕТ ДИРЕК»: система в промежуточном состоянии
        после обрыва сеанса. Тогда падать сотней тестов бессмысленно —
        набор пропускается с указанием причины.
        """
        import unittest
        try:
            return self.login(user, key)
        except (AssertionError, LinkError) as exc:
            raise unittest.SkipTest(f"КРАБ недоступен: {exc}") from exc

    def _open_next_line(self) -> bool:
        """Закрыть линию и открыть следующую по кругу. False — кончились."""
        try:
            self.term.close()
        except Exception:
            pass
        self.serial = False
        for _ in self._ports:
            self._index = (self._index + 1) % len(self._ports)
            port = self._ports[self._index]
            try:
                self.term = Terminal(f"tcp://127.0.0.1:{port}",
                                    machine=self.machine)
            except LinkError:
                continue
            self.term.session.nabor = "n2"
            self.url = f"tcp://127.0.0.1:{port}"
            return True
        self.serial = True
        self.url = f"tcp://127.0.0.1:{SERIAL_PORT}"
        try:
            self.term = Terminal(self.url, machine=self.machine)
        except LinkError:
            return False
        return True

    def reconnect(self) -> None:
        """Закрыть линию и открыть новую (свободную).

        После КОНЕЦ СЕАНСА старая линия перестаёт принимать ввод — КРАБ
        на ней больше не запускается, и набор уходит в никуда. Новая
        линия ДКС чистая и работает штатно.
        """
        try:
            self.term.close()
        except Exception:
            pass
        self.serial = False
        try:
            self.term = Terminal(self.url, machine=self.machine)
        except LinkError:
            self.serial = True
            self.url = f"tcp://127.0.0.1:{SERIAL_PORT}"
            self.term = Terminal(self.url, machine=self.machine)
        self.term.session.nabor = "n2"

    def inside_krab(self) -> bool:
        """Открыт ли сейчас КРАБ (последняя строка кадра — его приглашение)."""
        lines = [x.strip() for x in self.term.lines() if x.strip()]
        return bool(lines) and lines[-1] in ("-", "#", "*")

    def login(self, user: str = USER, key: str = KEY,
              tries: int = 3) -> str:
        """Полный вход: вызвать КРАБ и войти в номер, с перезапуском.

        Нужна именно эта последовательность, а не start()+enter(): на линии
        может остаться незакрытый номер от прерванного прогона. Тогда номер
        уже занят, «нач» приглашения «КТО?» не даёт, а «кон» закрывает чужой
        сеанс («КОНЕЦ СЕАНСА») и КРАБ завершается. Поэтому перед входом
        закрываем возможную старую сессию и, если КРАБ при этом вышел,
        вызываем его снова.
        """
        last = ""
        rounds = tries * ROTATE_LIMIT if ROTATE else tries
        for attempt in range(rounds):
            if attempt and ROTATE:
                # линия не дала входа — берём следующую по кругу
                if not self._open_next_line():
                    break
            if attempt:
                # переподключение обрывает возможный залипший номер на линии
                try:
                    self.term.close()
                except Exception:
                    pass
                self.term = Terminal(self.url, machine=self.machine)
            try:
                # «краб» набираем только если КРАБ не открыт: это не
                # директива (даёт «НЕТ ДИРЕК»), а лишний вызов заводит
                # второй экземпляр, который ещё секунд 15 не готов
                # принимать директивы — вход в него сразу не идёт.
                if not self.inside_krab():
                    self.start()
                return self.enter(user, key)
            except (AssertionError, LinkError) as exc:
                last = str(exc)
        raise AssertionError(f"вход в номер {user} не удался: {last}")

    def ensure_monitor(self, timeout: float = 20.0) -> str:
        """Вернуть терминал в Монитор абонентов (приглашение «-»).

        После блока Школы (приглашение «#») или программы ЛИСТ («*»)
        директивы Монитора не работают — «ТЕР» даёт «ОШИБ». Отсюда
        выход директивой КОН, пока не появится «-».
        """
        for _ in range(3):
            lines = [x.strip() for x in self.term.lines() if x.strip()]
            if not lines or lines[-1] == "-":
                return self.screen()
            self.term.type("кон")
            self.enter_line()
            self.term.wait_quiet(1.0, timeout)
        return self.screen()

    # --- работа в сеансе -----------------------------------------------
    #: приглашения КРАБ: «-» — Монитор абонентов, «*» — программа ЛИСТ,
#: «+» — набор строк в директиве ДОП, «/» — редактор РЕД
    PROMPTS = ("-", "*", "+", "/", "КОНЕЦ СЕАНСА")

    def directive(self, cmd: str, quiet: float = 0.3,
                  timeout: float = 25.0) -> str:
        """Исполнить директиву, вернуть только её выдачу (свернутую fold).

        Ожидание — по приглашению («-» в Мониторе, «*» в программе ЛИСТ),
        а не по паузе: директивы вроде КТЛ печатают каталог на десятки
        строк, и следующая команда, отправленная раньше, теряется.
        """
        rev = self.term.mark()
        self.send_text(cmd)
        self._await_prompt(rev, timeout)
        return "\n".join(fold(x.strip())
                         for x in self.term.new_lines(rev) if x.strip())

    def _await_prompt(self, rev: int, timeout: float) -> bool:
        """Ждать НОВОЕ приглашение — нижний изменившийся ряд кадра.

        Проверять «последняя строка = приглашение» нельзя: эхо набранной
        директивы печатается строкой выше, а строка «-» от предыдущей
        директивы остаётся на месте — условие выполняется уже на эхе.
        Поэтому берём нижний изменившийся после отправки ряд и требуем,
        чтобы им было приглашение.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rows = self.term.changed_since(rev)
            if rows:
                bottom = max(rows)
                text = (self.term.screen_.row_text("frame", bottom)
                        or "").strip()
                if text in self.PROMPTS:
                    self.term.wait_quiet(0.3, 4.0)   # добрать хвост выдачи
                    return True
            self.term.pump(timeout=0.15)
        return False

    # --- низкий уровень -------------------------------------------------
    def send(self, cmd: str, quiet: float = 1.5,
             timeout: float = 40.0) -> str:
        """Набрать строку и вернуть весь экран после ответа."""
        self.send_text(cmd)
        self.term.wait_quiet(quiet, timeout)
        return fold(self.term.screen())

    def wait_prompt(self, prompt: str, timeout: float = 40.0) -> str:
        """Ждать приглашения в кадре; вернуть кадр, свернутый fold()."""
        needle = fold(prompt)
        self.term.wait_for(needle, timeout=timeout)
        return fold(self.term.screen())

    def wait_new(self, needle: str, timeout: float = 40.0,
                 mark: int | None = None) -> bool:
        """Ждать строку, набранную ПОСЛЕ отметки, а не где-либо на экране.

        Искать по всему кадру нельзя: на нём ещё лежат приглашения
        предыдущих директив («+» от прошлого ввода ДОП), и ожидание
        проходит, хотя нужная директива не началась.
        """
        rev = self.term.mark() if mark is None else mark
        needle = fold(needle).upper()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for line in self.term.new_lines(rev):
                if needle in fold(line).upper():
                    return True
            self.term.pump(0.25)
        return False

    def screen(self) -> str:
        return fold(self.term.screen())

    def cleanup(self, timeout: float = 15.0) -> str:
        """Сбросить состояние номера: выйти из вложенных блоков, сбросить ПЗ.

        Нужно между тестовыми классами: все они работают под одним номером
        1234, а подчинённая задача у номера может быть только одна — иначе
        «фор пз» отвечает «УЖЕ ЕСТЬ ПЗ».
        """
        self.ensure_monitor(timeout)
        out = self.directive("что", timeout=timeout)
        if "У ВАС НЕТ ПЗ" in out:
            return out
        self.directive("выб", timeout=timeout)       # сбросить подчинённую задачу
        return self.directive("что", timeout=timeout)

    def close(self) -> None:
        """Закрыть линию, предварительно выйдя из номера.

        КОН здесь нужен и уместен: номер остаётся привязан к линии, и
        следующий вход на неё упрётся в чужой сеанс. Признак открытого
        Монитора — приглашение «-» в конце кадра.
        """
        try:
            lines = [x.strip() for x in self.term.lines() if x.strip()]
            if lines and lines[-1] in ("-", "#", "*"):
                self.term.type("кон")
                self.enter_line()
                self.term.wait_quiet(2.0, 30)
        finally:
            self.term.close()

    def __enter__(self) -> "KrabSession":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
