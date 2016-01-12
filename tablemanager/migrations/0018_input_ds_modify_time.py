# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0017_auto_20151124_1144'),
    ]

    operations = [
        migrations.AddField(
            model_name='input',
            name='ds_modify_time',
            field=models.DateTimeField(null=True, editable=False),
            preserve_default=True,
        ),
    ]
