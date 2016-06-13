# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import re
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0030_auto_20160404_1021'),
    ]

    operations = [
        migrations.AlterField(
            model_name='datasource',
            name='name',
            field=models.SlugField(help_text='The name of data source', unique=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z_][a-z0-9_]+$'), 'Slug can only start with lowercase letters or underscore, and contain lowercase letters, numbers and underscore', 'invalid')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='datasource',
            name='type',
            field=models.CharField(default='FileSystem', help_text='The type of data source', max_length=32, choices=[('FileSystem', 'FileSystem'), ('Database', 'Database'), ('Mudmap', 'Mudmap')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='foreigntable',
            name='name',
            field=models.SlugField(help_text='The name of foreign table', unique=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z_][a-z0-9_]+$'), 'Slug can only start with lowercase letters or underscore, and contain lowercase letters, numbers and underscore', 'invalid')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='input',
            name='name',
            field=models.SlugField(help_text='Name of table in harvest DB', unique=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z_][a-z0-9_]+$'), 'Slug can only start with lowercase letters or underscore, and contain lowercase letters, numbers and underscore', 'invalid')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='normalise',
            name='name',
            field=models.CharField(unique=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z_][a-z0-9_]+$'), 'Slug can only start with lowercase letters or underscore, and contain lowercase letters, numbers and underscore', 'invalid')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='normaltable',
            name='name',
            field=models.CharField(unique=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z_][a-z0-9_]+$'), 'Slug can only start with lowercase letters or underscore, and contain lowercase letters, numbers and underscore', 'invalid')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='publish',
            name='name',
            field=models.SlugField(help_text='Name of Publish', unique=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z_][a-z0-9_]+$'), 'Slug can only start with lowercase letters or underscore, and contain lowercase letters, numbers and underscore', 'invalid')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='publishchannel',
            name='name',
            field=models.SlugField(help_text='Name of publish destination', unique=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z_][a-z0-9_]+$'), 'Slug can only start with lowercase letters or underscore, and contain lowercase letters, numbers and underscore', 'invalid')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='replica',
            name='name',
            field=models.CharField(max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z_][a-z0-9_]+$'), 'Slug can only start with lowercase letters or underscore, and contain lowercase letters, numbers and underscore', 'invalid')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='style',
            name='name',
            field=models.SlugField(help_text='Name of Publish', max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z_][a-z0-9_]+$'), 'Slug can only start with lowercase letters or underscore, and contain lowercase letters, numbers and underscore', 'invalid')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='workspace',
            name='name',
            field=models.SlugField(help_text='Name of workspace', max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z_][a-z0-9_]+$'), 'Slug can only start with lowercase letters or underscore, and contain lowercase letters, numbers and underscore', 'invalid')]),
            preserve_default=True,
        ),
    ]
