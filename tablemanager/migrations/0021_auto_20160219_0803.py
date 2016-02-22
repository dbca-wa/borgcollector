# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion
import re
import tablemanager.models
import django.utils.timezone
import borg_utils.resource_status
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0020_workspace_auth_level'),
    ]

    operations = [
        migrations.CreateModel(
            name='Style',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.SlugField(help_text='Name of Publish', max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z0-9_]+$'), 'Slug can only contain lowercase letters, numbers and underscores', 'invalid')])),
                ('description', models.CharField(max_length=512, null=True, blank=True)),
                ('status', models.CharField(default=b'Enabled', max_length=32, choices=[(b'Enabled', b'Enabled'), (b'Disabled', b'Disabled')])),
                ('sld', tablemanager.models.XMLField(help_text='Styled Layer Descriptor', null=True, blank=True)),
                ('last_modify_time', models.DateTimeField(default=django.utils.timezone.now, auto_now_add=True)),
                ('publish', models.ForeignKey(to='tablemanager.Publish')),
            ],
            options={
                'ordering': ('publish', 'name'),
            },
            bases=(models.Model, borg_utils.resource_status.ResourceStatusManagement),
        ),
        migrations.AlterUniqueTogether(
            name='style',
            unique_together=set([('publish', 'name')]),
        ),
        migrations.AddField(
            model_name='publish',
            name='default_style',
            field=models.ForeignKey(related_name='+', on_delete=django.db.models.deletion.SET_NULL, to='tablemanager.Style', null=True),
            preserve_default=True,
        ),
    ]
