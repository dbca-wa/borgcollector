# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0006_slaveserver_last_poll_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='slaveserver',
            name='code_version',
            field=models.CharField(max_length=32, null=True, editable=False),
            preserve_default=True,
        ),
    ]
