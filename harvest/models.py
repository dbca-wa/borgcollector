import os

from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

from borg_utils.borg_config import BorgConfiguration

from tablemanager.models import Publish,downloadFileSystemStorage
from harvest.jobstates import JobState

def get_full_data_file_name(instance,filename):
    if instance.publish.workspace.workspace_as_schema:
        return 'full_data/{0}/{1}/{2}/{3}'.format(instance.publish.workspace.publish_channel.name,instance.publish.workspace.name,instance.batch_id,filename)
    else:
        return 'full_data/{0}/{1}/{2}'.format(instance.publish.workspace.publish_channel.name,instance.batch_id,filename)
        
class Job(models.Model):
    batch_id = models.CharField(max_length=64,null=False,editable=False)
    publish = models.ForeignKey(Publish,editable=False)
    state = models.CharField(max_length=64,null=False, editable=False)
    user_action = models.CharField(max_length=32,null=True,editable=False)
    retry_times = models.PositiveIntegerField(null=False,editable=False,default=0)
    last_execution_end_time = models.DateTimeField(default=timezone.now, editable=False,null=True)
    previous_state = models.CharField(max_length=64, null=True, editable=False)
    message = models.TextField(max_length=512, null = True, editable=False)
    created = models.DateTimeField(default=timezone.now, editable=False)
    launched = models.DateTimeField(null=True, blank=True, editable=False)
    finished = models.DateTimeField(null=True, blank=True, editable=False)
    job_type = models.CharField(max_length=32,default='Monthly',editable=False,null=False)
    pgdump_file = models.FileField(upload_to=get_full_data_file_name,storage=downloadFileSystemStorage,null=True,editable=False)
    style_file = models.FileField(upload_to=get_full_data_file_name,storage=downloadFileSystemStorage,null=True,editable=False)

    @property
    def normaltables(self):
        """
        the sorted related normal tables.
        """
        return self.publish.normaltables

    @property
    def normalises(self):
        """
        the sorted related normalises 
        """
        return self.publish.normalises

    @property 
    def is_manually_created(self):
        return self.job_type == Manually.instance().name

    @property
    def inputs(self):
        """
        related inputs.
        """
        return self.publish.inputs

    @property
    def dump_dir(self):
        if self.publish.workspace.workspace_as_schema:
            return os.path.join(BorgConfiguration.FULL_DATA_DUMP_DIR,self.publish.workspace.publish_channel.name, self.publish.workspace.name, self.batch_id)
        else:
            return os.path.join(BorgConfiguration.FULL_DATA_DUMP_DIR,self.publish.workspace.publish_channel.name, self.batch_id)

    def __str__(self):
        return str(self.pk)

    class Meta:
        unique_together = [['batch_id', 'publish']]

class JobEventListener(object):
    @staticmethod
    @receiver(pre_delete, sender=Job)
    def _pre_delete(sender, instance, **args):
        if instance.state and not JobState.get_jobstate(instance.state).is_end_state:
            raise Exception("Unfinished job can not be deleted.")
        #remove the dump file if exist
        if instance.pgdump_file:
            dump_path = instance.pgdump_file.path
            if os.path.isfile(dump_path):
                os.remove(dump_path)
            #remove the style file if exist
            if instance.style_file:
                style_path = instance.style_file.path
                if os.path.isfile(style_path):
                    os.remove(style_path)
            #remove the folder, if empty
            folder = os.path.dirname(dump_path)
            if os.path.exists(folder) and len(os.listdir(folder)) == 0:
                os.rmdir(folder)


class JobLog(models.Model):
    job = models.ForeignKey(Job,null=False,editable=False)
    state = models.CharField(max_length=64, editable=False)
    outcome = models.CharField(max_length=64, editable=False)
    message = models.TextField(max_length=512, null=True, editable=False)
    next_state = models.CharField(max_length=64, editable=False)
    start_time = models.DateTimeField(null=True, blank=True, editable=False)
    end_time = models.DateTimeField(null=True, blank=True, editable=False)

    def __str__(self):
        return "Log {0}".format(self.pk)
