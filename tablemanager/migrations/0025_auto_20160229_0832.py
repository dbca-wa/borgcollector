# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import tablemanager.models


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0024_auto_20160226_1239'),
    ]

    operations = [
        migrations.AddField(
            model_name='datasource',
            name='description',
            field=models.CharField(max_length=255, null=True, blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='datasource',
            name='password',
            field=models.CharField(max_length=320, null=True, blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='datasource',
            name='sql',
            field=tablemanager.models.SQLField(default="CREATE SERVER {{self.name}} FOREIGN DATA WRAPPER oracle_fdw OPTIONS (dbserver '//<hostname>/<sid>');", null=True, blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='datasource',
            name='user',
            field=models.CharField(max_length=320, null=True, blank=True),
            preserve_default=True,
        ),
    ]
