# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0029_auto_20160302_0750'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='publish',
            name='applications',
        ),
        migrations.AddField(
            model_name='publishchannel',
            name='gwc_endpoint',
            field=models.CharField(max_length=256, null=True, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='publishchannel',
            name='wfs_endpoint',
            field=models.CharField(max_length=256, null=True, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='publishchannel',
            name='wfs_version',
            field=models.CharField(max_length=32, null=True, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='publishchannel',
            name='wms_endpoint',
            field=models.CharField(max_length=256, null=True, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='publishchannel',
            name='wms_version',
            field=models.CharField(max_length=32, null=True, blank=True),
            preserve_default=True,
        ),
    ]
