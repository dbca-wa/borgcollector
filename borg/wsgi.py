"""
WSGI config for incredibus project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.6/howto/deployment/wsgi/
"""

import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "borg.settings")

import confy
try:
    confy.read_environment_file(".env")
except:
    pass

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
