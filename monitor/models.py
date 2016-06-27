import os

from django.db import models
from django.core.files.storage import FileSystemStorage
from django.conf import settings

from harvest.models import Job

class PreviewFileSystemStorage(FileSystemStorage):
    def __init__(self,**kwargs):
        kwargs["location"] = settings.PREVIEW_ROOT
        kwargs["base_url"] = settings.PREVIEW_URL
        super(PreviewFileSystemStorage,self).__init__(**kwargs)

    def save(self,name,content=None):
        #name should always points to a existing file.
        #import ipdb; ipdb.set_trace()
        return name
previewFileSystemStorage = PreviewFileSystemStorage()

def get_preview_file_name(instance,filename):
    if instance.workspace.workspace_as_schema:
        return '{0}/{1}/{2}/{3}'.format(instance.workspace.publish_channel.name,instance.workspace.name,instance.job_batch_id,filename)
    else:
        return '{0}/{1}/{2}'.format(instance.workspace.publish_channel.name,instance.job_batch_id,filename)

class SlaveServer(models.Model):
    name = models.CharField(max_length=64,null=False,editable=False)
    listen_channels = models.CharField(max_length=255,null=False,editable=False)
    register_time = models.DateTimeField(null=True, blank=True, editable=False)
    last_poll_time = models.DateTimeField(null=True, blank=True, editable=False)
    last_sync_time = models.DateTimeField(null=True, blank=True, editable=False)
    last_sync_message = models.TextField(null=True,editable=False)
    code_version = models.CharField(max_length=32,null=True,editable=False)

    def __str__(self):
        return self.name

class PublishSyncStatus(models.Model):
    slave_server = models.ForeignKey(SlaveServer,null=False,editable=False)
    publish = models.CharField(max_length=255, null=False, editable=False,db_index=True)
    spatial_type = models.CharField(max_length=255,null=True,editable=False)
    deploied_job_id = models.IntegerField(null=True,editable=False,db_index=True)
    deploied_job_batch_id = models.CharField(max_length=64,null=True,editable=False)
    deploy_message = models.TextField(null=True,editable=False)
    deploy_time = models.DateTimeField(null=True, editable=False)
    preview_file = models.FileField(upload_to=get_preview_file_name,storage=previewFileSystemStorage,null=True,editable=False)
    sync_job_id = models.IntegerField(null=True,editable=False,db_index=True)
    sync_job_batch_id = models.CharField(max_length=64,null=True,editable=False)
    sync_message = models.TextField(null=True,editable=False)
    sync_time = models.DateTimeField(null=True, editable=False)
    

    def __str__(self):
        return "{0}:{1}".format(self.slave_server.name,self.publish)

    class Meta:
        verbose_name = "Publish sync status"
        verbose_name_plural = "Publishs sync status"
        unique_together = (('slave_server','publish'),)
        ordering = ['sync_time','-deploy_time','slave_server','publish']


class TaskSyncStatus(models.Model):
    slave_server = models.ForeignKey(SlaveServer,null=False,editable=False)
    task_type = models.CharField(max_length=255, null=False, editable=False,db_index=True)
    task_name = models.CharField(max_length=255, null=False, editable=False,db_index=True)
    action = models.CharField(max_length=32, null=False, editable=False,db_index=True,default='update')
    preview_file = models.FileField(upload_to=get_preview_file_name,storage=previewFileSystemStorage,null=True,editable=False)
    sync_succeed = models.BooleanField(null=False,editable=False,default=False)
    sync_message = models.TextField(null=True,editable=False)
    sync_time = models.DateTimeField(null=True, editable=False)

    def __str__(self):
        return "{1} {0}:{2}".format(self.slave_server.name,self.task_type,self.task_name)

    class Meta:
        verbose_name = "Task sync status"
        verbose_name_plural = "Task sync status"
        unique_together = (('slave_server','task_type','task_name','action'),)
        ordering = ['sync_succeed','-sync_time']
        
