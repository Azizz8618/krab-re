"""Пути для тестов: каталог tests/ добавляется в sys.path (krab_session.py),
эмулятор 15ИЭ — из IE15_HOME (по умолчанию ~/Yandex.Disk/ie15).

Линии ДКС задаются переменной KRAB_PORT (по умолчанию 4202-4223 — все
линии tty dispak.ini).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (str(HERE), str(Path(os.environ.get("IE15_HOME",
                                            Path.home() / "Yandex.Disk" / "ie15")))):
    if p not in sys.path:
        sys.path.insert(0, p)
