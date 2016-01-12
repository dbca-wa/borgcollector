# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PublishSyncStatus',
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
                'verbose_name': 'Publish sync status',
                'verbose_name_plural': 'Publishs sync status',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='TaskSyncStatus',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('task_type', models.CharField(max_length=255, editable=False, db_index=True)),
                ('task_name', models.CharField(max_length=255, editable=False, db_index=True)),
                ('sync_status', models.BooleanField(editable=False)),
                ('sync_message', models.TextField(null=True, editable=False)),
                ('sync_time', models.DateTimeField(null=True, editable=False)),
                ('slave_server', models.ForeignKey(editable=False, to='monitor.SlaveServer')),
            ],
            options={
                'verbose_name': 'Task sync status',
                'verbose_name_plural': 'Task sync status',
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='slaveserversyncstatus',
            unique_together=None,
        ),
        migrations.RemoveField(
            model_name='slaveserversyncstatus',
            name='slave_server',
        ),
        migrations.DeleteModel(
            name='SlaveServerSyncStatus',
        ),
        migrations.AlterUniqueTogether(
            name='tasksyncstatus',
            unique_together=set([('slave_server', 'task_type', 'task_name')]),
        ),
        migrations.AlterUniqueTogether(
            name='publishsyncstatus',
            unique_together=set([('slave_server', 'publish')]),
        ),
    ]
