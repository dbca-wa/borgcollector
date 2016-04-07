# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import re
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('wmsmanager', '0006_auto_20160330_0837'),
    ]

    operations = [
        migrations.AlterField(
            model_name='wmslayer',
            name='kmi_name',
            field=models.SlugField(max_length=128, validators=[django.core.validators.RegexValidator(re.compile(b'^[a-z0-9_]+$'), b'Slug can only contain lowercase letters, numbers and underscores', b'invalid')]),
            preserve_default=True,
        ),
    ]
