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

#: шифр пользователя для тестов (первые 4 цифры — шифр ОС Диспак)
USER = "1234"
#: ключ-пароль пользователя
KEY = "1234"

#: спецификация линий ДКС (dispak.ini: 4199=tty2 … 4223=tty24);
#: TCPLink сам обходит занятые линии и берёт первую свободную
PORT_SPEC = os.environ.get("KRAB_PORT", "4202-4223")


class KrabSession:
    """Сеанс КРАБ на линии ДКС, управляемый как человеком-оператором."""

    def __init__(self, port: str = PORT_SPEC, machine: str = "6") -> None:
        self.term = Terminal(f"tcp://127.0.0.1:{port}", machine=machine)

    # --- протокол входа ------------------------------------------------
    def start(self, timeout: float = 40.0) -> str:
        """Вызвать КРАБ и дождаться баннера и приглашения «-»."""
        self.term.drain(quiet=0.5, timeout=10)
        self.term.key("KEY_ENTER")
        self.term.wait_quiet(1.0, 25)          # приглашение «ЭВМ-3,TNNN»
        self.term.type("краб")
        self.term.key("KEY_ENTER")
        # ждём по содержимому, а не по таймеру: на загруженной машине
        # баннер «** К  Р  А  Б ** (ВЕР.xx ОТ …)» печатается с задержкой
        self.term.wait_for("BEP.", timeout=timeout)   # латентная часть баннера
        self.term.wait_for("ОT ", timeout=timeout)
        text = fold(self.term.screen())
        assert "К  Р  А  Б" in text and "ВЕР." in text, \
            f"нет баннера КРАБ: {text!r}"
        return text

    def enter(self, user: str = USER, key: str = KEY,
              timeout: float = 40.0, tries: int = 2) -> str:
        """Вход: «нач» → КТО? → шифр → КЛЮЧ- → ключ.

        Приглашения проверяются по содержимому, а не по паузе: на линии
        может остаться незакрытый номер от прошлого сеанса, тогда «нач»
        не даёт «КТО?», и шифр ушёл бы как директива («НЕТ ДИРЕК»).
        В этом случае линия «чистится» (кон, пустая посылка) и вход
        повторяется.
        """
        for attempt in range(tries):
            self.send("нач", 1.5, timeout)
            if not self.term.wait_for("KTО?", timeout=timeout):
                # приглашения нет — номер занят другой сессией;
                # этот случай разбирает login()
                continue
            self.send(user, 1.5, timeout)
            if not self.term.wait_for("KЛЮЧ", timeout=timeout):
                continue
            self.send(key, 1.5, timeout)
            # сеанс открыт, если машина требует директиву приглашением «-»
            if "СООБЩИТЕ ВАШ НОМЕР" not in self.screen():
                return self.screen()
        raise AssertionError(f"не удалось войти в номер {user}: "
                             f"{self.screen()!r}")

    def exit(self, timeout: float = 40.0) -> str:
        """Окончание работы в номере (директива КОН)."""
        return self.send("кон", 3.0, timeout)

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
        for _ in range(tries):
            # если КРАБ уже вызван (повторный вход внутри сеанса), «краб»
            # не набираем — это не директива и даст «НЕТ ДИРЕК»
            if "К  Р  А  Б" not in self.screen():
                self.start()
            self.send("кон", 1.5, 25)               # закрыть повисший сеанс
            if "К  Р  А  Б" not in self.screen():   # КРАБ вышел — вызвать снова
                self.start()
            try:
                return self.enter(user, key, tries=1)
            except AssertionError as exc:
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
            self.term.key("KEY_ENTER")
            self.term.wait_quiet(1.5, timeout)
        return self.screen()

    # --- работа в сеансе -----------------------------------------------
    #: приглашения КРАБ: «-» — Монитор абонентов, «*» — программа ЛИСТ,
#: «+» — набор строк в директиве ДОП, «/» — редактор РЕД
    PROMPTS = ("-", "*", "+", "/", "КОНЕЦ СЕАНСА")

    def directive(self, cmd: str, quiet: float = 0.4,
                  timeout: float = 20.0) -> str:
        """Исполнить директиву, вернуть только её выдачу (свернутую fold).

        Ожидание — по приглашению («-» в Мониторе, «*» в программе ЛИСТ),
        а не по паузе: директивы вроде КТЛ печатают каталог на десятки
        строк, и следующая команда, отправленная раньше, теряется.
        """
        rev = self.term.mark()
        self.term.type(cmd)
        self.term.key("KEY_ENTER")
        self._await_prompt(rev, timeout)
        return "\n".join(fold(x.strip())
                         for x in self.term.new_lines(rev) if x.strip())

    def _await_prompt(self, rev: int, timeout: float) -> bool:
        """Ждать НОВОЕ приглашение: последняя строка кадра — «-»/«*».

        Отметка `rev` обязательна: приглашение от предыдущей директивы ещё
        стоит последней строкой, и без проверки «изменилось ли после
        отправки» метод возвращал бы пустой результат мгновенно.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            lines = [x.rstrip() for x in self.term.lines() if x.strip()]
            if (lines and lines[-1].strip() in self.PROMPTS
                    and self.term.screen_.rev != rev):
                self.term.wait_quiet(0.4, 5)      # добрать хвост выдачи
                return True
            self.term.pump(timeout=0.15)
        return False

    # --- низкий уровень -------------------------------------------------
    def send(self, cmd: str, quiet: float = 1.5,
             timeout: float = 40.0) -> str:
        """Набрать строку и вернуть весь экран после ответа."""
        self.term.type(cmd)
        self.term.key("KEY_ENTER")
        self.term.wait_quiet(quiet, timeout)
        return fold(self.term.screen())

    def wait_prompt(self, prompt: str, timeout: float = 40.0) -> str:
        """Ждать приглашения в кадре; вернуть кадр, свернутый fold()."""
        needle = fold(prompt)
        self.term.wait_for(needle, timeout=timeout)
        return fold(self.term.screen())

    def screen(self) -> str:
        return fold(self.term.screen())

    def close(self) -> None:
        """Выйти из номера и закрыть линию (буфер вывода надо опустошить)."""
        try:
            if "** K  P  A  B **" in self.screen():
                self.term.type("кон")
                self.term.key("KEY_ENTER")
                self.term.wait_quiet(2.0, 30)
        finally:
            self.term.close()

    def __enter__(self) -> "KrabSession":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
