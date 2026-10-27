"""Делает папку импортируемой из любого места репозитория:
    from add.orchestrator import Orchestrator      (вместо add подставьте имя вашей папки)
Модули внутри папки импортируют друг друга без имени пакета (from cities import ...),
поэтому при импорте папки добавляем её в sys.path."""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
