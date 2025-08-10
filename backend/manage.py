#!/usr/bin/env python
"""Утилита командной строки Django для управления проектом.

Все комментарии и docstring — на русском языке в соответствии с требованиями.
"""
import os
import sys


def main() -> None:
    """Точка входа для команд Django."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

