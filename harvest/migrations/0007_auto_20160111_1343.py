# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('harvest', '0006_job_is_manually_created'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='job',
            name='is_manually_created',
        ),
        migrations.AddField(
            model_name='job',
            name='job_type',
            field=models.CharField(default=b'Monthly', max_length=32, editable=False),
            preserve_default=True,
        ),
    ]
