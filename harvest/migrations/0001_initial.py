# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone
import harvest.models
import tablemanager.models


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Job',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('batch_id', models.CharField(max_length=64, editable=False)),
                ('state', models.CharField(max_length=64, editable=False)),
                ('previous_state', models.CharField(max_length=64, null=True, editable=False)),
                ('message', models.TextField(max_length=512, null=True, editable=False)),
                ('created', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('launched', models.DateTimeField(null=True, editable=False, blank=True)),
                ('finished', models.DateTimeField(null=True, editable=False, blank=True)),
                ('pgdump_file', models.FileField(null=True, editable=False)),
                ('style_file', models.FileField(null=True, editable=False)),
                ('publish', models.ForeignKey(editable=False, to='tablemanager.Publish')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='JobLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('state', models.CharField(max_length=64, editable=False)),
                ('outcome', models.CharField(max_length=64, editable=False)),
                ('message', models.TextField(max_length=512, null=True, editable=False)),
                ('next_state', models.CharField(max_length=64, editable=False)),
                ('start_time', models.DateTimeField(null=True, editable=False, blank=True)),
                ('end_time', models.DateTimeField(null=True, editable=False, blank=True)),
                ('job', models.ForeignKey(editable=False, to='harvest.Job')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='job',
            unique_together=set([('batch_id', 'publish')]),
        ),
    ]
