# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='SlaveServer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=64, editable=False)),
                ('listen_channels', models.CharField(max_length=255, editable=False)),
                ('register_time', models.DateTimeField(null=True, editable=False, blank=True)),
                ('last_sync_time', models.DateTimeField(null=True, editable=False, blank=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='SlaveServerSyncStatus',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('publish', models.CharField(max_length=255, editable=False, db_index=True)),
                ('deploied_job_id', models.IntegerField(null=True, editable=False, db_index=True)),
                ('deploied_job_batch_id', models.CharField(max_length=64, null=True, editable=False)),
                ('deploy_message', models.TextField(null=True, editable=False)),
                ('deploy_time', models.DateTimeField(null=True, editable=False)),
                ('sync_job_id', models.IntegerField(null=True, editable=False, db_index=True)),
                ('sync_job_batch_id', models.CharField(max_length=64, null=True, editable=False)),
                ('sync_message', models.TextField(null=True, editable=False)),
                ('sync_time', models.DateTimeField(null=True, editable=False)),
                ('slave_server', models.ForeignKey(editable=False, to='monitor.SlaveServer')),
            ],
            options={
                'verbose_name': 'Slave server sync status',
                'verbose_name_plural': 'Slave servers sync status',
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='slaveserversyncstatus',
            unique_together=set([('slave_server', 'publish')]),
        ),
    ]
