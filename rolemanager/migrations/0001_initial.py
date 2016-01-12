# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import rolemanager.models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Role',
            fields=[
                ('name', models.CharField(max_length=64, serialize=False, editable=False, primary_key=True)),
                ('status', models.CharField(max_length=16, editable=False, choices=[(b'New', b'New'), (b'Remove', b'Remove'), (b'Update', b'Update'), (b'Synced', b'Synced'), (b'Removed', b'Removed')])),
                ('last_sync_time', models.DateTimeField(null=True, editable=False)),
                ('last_update_time', models.DateTimeField(editable=False)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='SyncLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('sync_time', models.DateTimeField(null=True, editable=False)),
                ('automatic', models.BooleanField(default=True, editable=False)),
                ('load_status', models.CharField(max_length=32, null=True, editable=False)),
                ('commit_status', models.CharField(max_length=32, null=True, editable=False)),
                ('push_status', models.CharField(max_length=32, null=True, editable=False)),
                ('message', models.TextField(null=True, editable=False)),
                ('end_time', models.DateTimeField(null=True, editable=False)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='User',
            fields=[
                ('name', models.CharField(max_length=128, serialize=False, editable=False, primary_key=True)),
                ('synced_roles', rolemanager.models.StringListField(sort=False, max_length=256, null=True, editable=False)),
                ('latest_roles', rolemanager.models.StringListField(sort=False, max_length=256, null=True, editable=False)),
                ('status', models.CharField(max_length=16, editable=False, choices=[(b'New', b'New'), (b'Remove', b'Remove'), (b'Update', b'Update'), (b'Synced', b'Synced'), (b'Removed', b'Removed')])),
                ('last_sync_time', models.DateTimeField(null=True, editable=False)),
                ('last_update_time', models.DateTimeField(editable=False)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
    ]
