# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import re
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('wmsmanager', '0007_auto_20160405_0913'),
    ]

    operations = [
        migrations.AlterField(
            model_name='wmslayer',
            name='kmi_name',
            field=models.SlugField(max_length=128, validators=[django.core.validators.RegexValidator(re.compile(b'^[a-z_][a-z0-9_]+$'), b'Slug can only start with lowercase letters or underscore, and contain lowercase letters, numbers and underscore', b'invalid')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='wmsserver',
            name='name',
            field=models.SlugField(primary_key=True, serialize=False, max_length=64, validators=[django.core.validators.RegexValidator(re.compile(b'^[a-z_][a-z0-9_]+$'), b'Slug can only start with lowercase letters or underscore, and contain lowercase letters, numbers and underscore', b'invalid')], help_text=b'The name of wms server'),
            preserve_default=True,
        ),
    ]
