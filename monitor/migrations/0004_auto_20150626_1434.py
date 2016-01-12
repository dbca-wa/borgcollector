# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0003_auto_20150626_1420'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='publishsyncstatus',
            options={'ordering': ['slave_server', 'publish'], 'verbose_name': 'Publish sync status', 'verbose_name_plural': 'Publishs sync status'},
        ),
        migrations.AlterModelOptions(
            name='tasksyncstatus',
            options={'ordering': ['slave_server', 'task_type', 'task_name'], 'verbose_name': 'Task sync status', 'verbose_name_plural': 'Task sync status'},
        ),
        migrations.RenameField(
            model_name='tasksyncstatus',
            old_name='sync_status',
            new_name='sync_succeed',
        ),
    ]
