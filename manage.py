#!/usr/bin/env python
import sys
import confy
import os

try:
    confy.read_environment_file()
except:
    pass
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "borg.settings")

if __name__ == "__main__":
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
