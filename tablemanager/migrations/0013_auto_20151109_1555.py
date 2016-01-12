# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import re
import tablemanager.models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0012_merge'),
    ]

    operations = [
        migrations.AddField(
            model_name='publish',
            name='sld',
            field=tablemanager.models.XMLField(help_text='Styled Layer Descriptor', null=True, blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='datasource',
            name='name',
            field=models.SlugField(help_text='The name of data source', unique=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z0-9_]+$'), 'Slug can only contain lowercase letters, numbers and underscores', 'invalid')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='foreignserver',
            name='name',
            field=models.SlugField(help_text='The name of foreign server', unique=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z0-9_]+$'), 'Slug can only contain lowercase letters, numbers and underscores', 'invalid')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='foreigntable',
            name='name',
            field=models.SlugField(help_text='The name of foreign table', unique=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z0-9_]+$'), 'Slug can only contain lowercase letters, numbers and underscores', 'invalid')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='publish',
            name='name',
            field=models.SlugField(help_text='Name of Publish', unique=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z0-9_]+$'), 'Slug can only contain lowercase letters, numbers and underscores', 'invalid')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='workspace',
            name='name',
            field=models.SlugField(help_text='Name of workspace', unique=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z0-9_]+$'), 'Slug can only contain lowercase letters, numbers and underscores', 'invalid')]),
            preserve_default=True,
        ),
    ]
