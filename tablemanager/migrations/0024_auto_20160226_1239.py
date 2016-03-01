# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import tablemanager.models


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0023_auto_20160219_1402'),
    ]

    operations = [
        migrations.AddField(
            model_name='datasource',
            name='password',
            field=models.CharField(max_length=320, null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='datasource',
            name='sql',
            field=tablemanager.models.SQLField(default="CREATE SERVER {{self.name}} FOREIGN DATA WRAPPER oracle_fdw OPTIONS (dbserver '//<hostname>/<sid>');"),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='datasource',
            name='type',
            field=models.CharField(default='FileSystem', help_text='The type of data source', max_length=32, choices=[('FileSystem', 'FileSystem'), ('Oracle', 'Oracle')]),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='datasource',
            name='user',
            field=models.CharField(max_length=320, null=True),
            preserve_default=True,
        ),
    ]
