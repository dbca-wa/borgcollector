# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('harvest', '0008_process'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='job',
            name='pgdump_file',
        ),
        migrations.RemoveField(
            model_name='job',
            name='style_file',
        ),
        migrations.AddField(
            model_name='job',
            name='metadata',
            field=models.TextField(null=True, editable=False),
            preserve_default=True,
        ),
    ]
