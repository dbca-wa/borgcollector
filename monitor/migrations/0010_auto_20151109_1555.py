# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0009_auto_20151021_1256'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='tasksyncstatus',
            options={'ordering': ['sync_succeed', '-sync_time'], 'verbose_name': 'Task sync status', 'verbose_name_plural': 'Task sync status'},
        ),
    ]
