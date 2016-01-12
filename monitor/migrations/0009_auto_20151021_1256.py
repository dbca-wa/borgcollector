# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0008_publishsyncstatus_preview_file'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='publishsyncstatus',
            options={'ordering': ['sync_time', '-deploy_time', 'slave_server', 'publish'], 'verbose_name': 'Publish sync status', 'verbose_name_plural': 'Publishs sync status'},
        ),
        migrations.AddField(
            model_name='publishsyncstatus',
            name='spatial_type',
            field=models.CharField(max_length=255, null=True, editable=False),
            preserve_default=True,
        ),
    ]
