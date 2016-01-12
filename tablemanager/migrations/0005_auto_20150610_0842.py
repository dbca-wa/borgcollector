# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0004_auto_20150609_1502'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='publish',
            name='applications',
        ),
        migrations.DeleteModel(
            name='Application',
        ),
    ]
