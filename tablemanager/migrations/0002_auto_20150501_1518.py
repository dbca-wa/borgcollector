# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import tablemanager.models


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='input',
            name='importing_info',
            field=models.TextField(max_length=255, null=True, editable=False),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='foreigntable',
            name='sql',
            field=tablemanager.models.SQLField(default="CREATE FOREIGN TABLE {{schema}}.{{self.name}} () SERVER {{self.server.name}} OPTIONS (schema '<schema>', table '<table>');"),
            preserve_default=True,
        ),
    ]
