# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone
import borg_utils.resource_status


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0007_auto_20150610_1156'),
    ]

    operations = [
        migrations.CreateModel(
            name='WmsLayer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=128)),
                ('title', models.CharField(max_length=512, null=True, editable=False)),
                ('abstract', models.TextField(null=True, editable=False)),
                ('kmi_name', models.CharField(max_length=128, null=True, blank=True)),
                ('kmi_title', models.CharField(max_length=512, null=True, blank=True)),
                ('kmi_abstract', models.TextField(null=True, blank=True)),
                ('path', models.CharField(max_length=512, null=True, editable=False)),
                ('applications', models.TextField(null=True, editable=False, blank=True)),
                ('geoserver_setting', models.TextField(null=True, editable=False, blank=True)),
                ('status', models.CharField(max_length=16, editable=False, choices=[(b'New', b'New'), (b'Updated', b'Updated'), (b'Unpublished', b'Unpublished'), (b'Published', b'Published')])),
                ('last_publish_time', models.DateTimeField(null=True, editable=False)),
                ('last_unpublish_time', models.DateTimeField(null=True, editable=False)),
                ('last_refresh_time', models.DateTimeField(editable=False)),
                ('last_modify_time', models.DateTimeField(null=True, editable=False)),
            ],
            options={
                'ordering': ('server', 'name'),
            },
            bases=(models.Model, borg_utils.resource_status.ResourceStatusMixin),
        ),
        migrations.CreateModel(
            name='WmsServer',
            fields=[
                ('name', models.CharField(max_length=64, serialize=False, primary_key=True)),
                ('capability_url', models.CharField(max_length=256)),
                ('user', models.CharField(max_length=32, null=True, blank=True)),
                ('password', models.CharField(max_length=32, null=True, blank=True)),
                ('geoserver_setting', models.TextField(null=True, editable=False, blank=True)),
                ('layers', models.PositiveIntegerField(default=0, editable=False)),
                ('status', models.CharField(max_length=16, editable=False, choices=[(b'New', b'New'), (b'Updated', b'Updated'), (b'Published', b'Published'), (b'Unpublished', b'Unpublished')])),
                ('last_refresh_time', models.DateTimeField(null=True, editable=False)),
                ('last_publish_time', models.DateTimeField(null=True, editable=False)),
                ('last_unpublish_time', models.DateTimeField(null=True, editable=False)),
                ('last_modify_time', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('workspace', models.ForeignKey(to='tablemanager.Workspace')),
            ],
            options={
            },
            bases=(models.Model, borg_utils.resource_status.ResourceStatusMixin),
        ),
        migrations.AddField(
            model_name='wmslayer',
            name='server',
            field=models.ForeignKey(editable=False, to='wmsmanager.WmsServer'),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='wmslayer',
            unique_together=set([('server', 'name'), ('server', 'kmi_name')]),
        ),
        migrations.CreateModel(
            name='InterestedWmsLayer',
            fields=[
            ],
            options={
                'verbose_name': 'Wms layer (Interested)',
                'proxy': True,
                'verbose_name_plural': 'Wms layers (Interested)',
            },
            bases=('wmsmanager.wmslayer',),
        ),
        migrations.CreateModel(
            name='PublishedWmsLayer',
            fields=[
            ],
            options={
                'verbose_name': 'Wms layer (Published)',
                'proxy': True,
                'verbose_name_plural': 'Wms layers (Published)',
            },
            bases=('wmsmanager.wmslayer',),
        ),
    ]
