# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0011_tasksyncstatus_action'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tasksyncstatus',
            name='action',
            field=models.CharField(default=b'update', max_length=32, editable=False, db_index=True),
            preserve_default=True,
        ),
    ]
