# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import re
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('wmsmanager', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='wmslayer',
            name='name',
            field=models.SlugField(help_text=b'The name of wms layer', max_length=128, validators=[django.core.validators.RegexValidator(re.compile(b'^[a-z0-9_]+$'), b'Slug can only contain lowercase letters, numbers and underscores', b'invalid')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='wmsserver',
            name='name',
            field=models.SlugField(primary_key=True, serialize=False, max_length=64, validators=[django.core.validators.RegexValidator(re.compile(b'^[a-z0-9_]+$'), b'Slug can only contain lowercase letters, numbers and underscores', b'invalid')], help_text=b'The name of wms server'),
            preserve_default=True,
        ),
    ]
