# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone
import borg_utils.resource_status
import borg_utils.signal_enable


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0007_auto_20150610_1156'),
        ('wmsmanager', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='LayerGroup',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(unique=True, max_length=128)),
                ('title', models.CharField(max_length=320, null=True, blank=True)),
                ('srs', models.CharField(max_length=320, choices=[(b'EPSG:4283', b'EPSG:4283'), (b'EPSG:4326', b'EPSG:4426')])),
                ('abstract', models.TextField(null=True, blank=True)),
                ('geoserver_setting', models.TextField(null=True, editable=False, blank=True)),
                ('status', models.CharField(max_length=16, editable=False, choices=[(b'New', b'New'), (b'Updated', b'Updated'), (b'Published', b'Published'), (b'Unpublished', b'Unpublished')])),
                ('last_publish_time', models.DateTimeField(null=True, editable=False)),
                ('last_unpublish_time', models.DateTimeField(null=True, editable=False)),
                ('last_modify_time', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('workspace', models.ForeignKey(to='tablemanager.Workspace')),
            ],
            options={
                'ordering': ['workspace', 'name'],
            },
            bases=(models.Model, borg_utils.resource_status.ResourceStatusManagement, borg_utils.signal_enable.SignalEnable),
        ),
        migrations.CreateModel(
            name='LayerGroupLayers',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('order', models.PositiveIntegerField()),
                ('group', models.ForeignKey(related_name='+', to='layergroup.LayerGroup')),
                ('layer', models.ForeignKey(to='wmsmanager.WmsLayer', null=True)),
                ('publish', models.ForeignKey(blank=True, editable=False, to='tablemanager.Publish', null=True)),
                ('sub_group', models.ForeignKey(related_name='+', blank=True, editable=False, to='layergroup.LayerGroup', null=True)),
            ],
            options={
                'ordering': ['group', 'order'],
                'verbose_name': 'Layer group layers',
                'verbose_name_plural': 'Layer group layers',
            },
            bases=(models.Model, borg_utils.signal_enable.SignalEnable),
        ),
        migrations.AlterUniqueTogether(
            name='layergrouplayers',
            unique_together=set([('group', 'order'), ('group', 'layer', 'sub_group')]),
        ),
    ]
