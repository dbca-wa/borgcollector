# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0025_auto_20160229_0832'),
    ]

    operations = [
        migrations.AlterField(
            model_name='datasource',
            name='type',
            field=models.CharField(default='FileSystem', help_text='The type of data source', max_length=32, choices=[('FileSystem', 'FileSystem'), ('Database', 'Database')]),
            preserve_default=True,
        ),
    ]
