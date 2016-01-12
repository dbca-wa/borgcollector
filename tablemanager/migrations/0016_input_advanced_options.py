# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0015_workspace_allow_authenticated'),
    ]

    operations = [
        migrations.AddField(
            model_name='input',
            name='advanced_options',
            field=models.CharField(help_text='Advanced ogr2ogr options', max_length=128, null=True, blank=True),
            preserve_default=True,
        ),
    ]
