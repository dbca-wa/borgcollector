# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('harvest', '0004_auto_20150525_1456'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='last_execution_end_time',
            field=models.DateTimeField(default=django.utils.timezone.now, null=True, editable=False),
            preserve_default=True,
        ),
    ]
