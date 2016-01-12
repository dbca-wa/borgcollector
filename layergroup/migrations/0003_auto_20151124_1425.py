# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import re
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('layergroup', '0002_auto_20150626_1419'),
    ]

    operations = [
        migrations.AlterField(
            model_name='layergroup',
            name='name',
            field=models.SlugField(help_text=b'The name of layer group', unique=True, max_length=128, validators=[django.core.validators.RegexValidator(re.compile(b'^[a-z0-9_]+$'), b'Slug can only contain lowercase letters, numbers and underscores', b'invalid')]),
            preserve_default=True,
        ),
    ]
