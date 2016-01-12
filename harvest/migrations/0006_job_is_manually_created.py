# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('harvest', '0005_job_last_execution_end_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='is_manually_created',
            field=models.BooleanField(default=False, editable=False),
            preserve_default=True,
        ),
    ]
