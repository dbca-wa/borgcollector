# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0002_auto_20150626_1419'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tasksyncstatus',
            name='sync_status',
            field=models.BooleanField(default=False, editable=False),
            preserve_default=True,
        ),
    ]
