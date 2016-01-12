# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('harvest', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='retry_times',
            field=models.PositiveIntegerField(default=0, editable=False),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='job',
            name='user_action',
            field=models.CharField(max_length=32, null=True, editable=False),
            preserve_default=True,
        ),
    ]
