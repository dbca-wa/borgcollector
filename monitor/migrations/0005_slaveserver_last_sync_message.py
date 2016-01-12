# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0004_auto_20150626_1434'),
    ]

    operations = [
        migrations.AddField(
            model_name='slaveserver',
            name='last_sync_message',
            field=models.TextField(null=True, editable=False),
            preserve_default=True,
        ),
    ]
