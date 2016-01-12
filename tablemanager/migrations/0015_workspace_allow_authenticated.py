# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0014_remove_input_sld'),
    ]

    operations = [
        migrations.AddField(
            model_name='workspace',
            name='allow_authenticated',
            field=models.BooleanField(default=False),
            preserve_default=True,
        ),
    ]
