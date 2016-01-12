# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0010_auto_20151109_1555'),
    ]

    operations = [
        migrations.AddField(
            model_name='tasksyncstatus',
            name='action',
            field=models.CharField(default=b'Update', max_length=32, editable=False, db_index=True),
            preserve_default=True,
        ),
    ]
