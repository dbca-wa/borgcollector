# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0005_slaveserver_last_sync_message'),
    ]

    operations = [
        migrations.AddField(
            model_name='slaveserver',
            name='last_poll_time',
            field=models.DateTimeField(null=True, editable=False, blank=True),
            preserve_default=True,
        ),
    ]
