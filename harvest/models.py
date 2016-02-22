import os
import socket
import json
from datetime import timedelta

from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

from borg_utils.borg_config import BorgConfiguration

from tablemanager.models import Publish
from harvest.jobstates import JobState
from borg_utils.jobintervals import Manually

class Process(models.Model):
    current_server=socket.getfqdn()
    current_pid=os.getpid()

    name = models.CharField(max_length=32,null=False,editable=False)
    desc = models.CharField(max_length=256,null=False,editable=False)
    server = models.CharField(max_length=64,null=False,editable=False)
    pid = models.IntegerField(max_length=64,null=False,editable=False)
    status = models.CharField(max_length=32,null=False,editable=False)
    last_message = models.TextField(null=True,editable=False)
    last_starttime = models.DateTimeField(null=True, editable=False)
    last_endtime = models.DateTimeField(null=True, editable=False)
    next_scheduled_time = models.DateTimeField(null=False, editable=False)

    @property
    def is_alive(self):
        """
        check whether process is alive or not.
        """
        if self.pid:
            if self.current_server == self.server and self.current_pid == self.pid:
                #same process
                return True
            else:
                if self.current_server == self.server:
                    #same server
                    if not os.path.exists(os.path.join("/proc",str(self.pid))):
                        return False
                #not the same process, check the heatbeat
                if self.status == "shutdown":
                    return False
                else:
                    return True
        else:
            return False

    @property
    def can_run(self):
        """
        At any time, only one process can run .
        Return True, if can run; otherwise return false
        """
        if self.is_alive:
            #the proess is alive, can run only if the process is the same process as the checking process
            return self.current_server == self.server and self.current_pid == self.pid
        else:
            return True

    @property
    def same_process(self):
        return self.current_server == self.server and self.current_pid == self.pid
        

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
    metadata = models.TextField(null = True, editable=False)

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
    def metadict(self):
        if hasattr(self,"_metadict"):
            return self._metadict
        else:
            setattr(self,"_metadict",json.loads(self.metadata) if self.metadata else {})
            return self._metadict

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
        dump_dir = instance.dump_dir
        if os.path.exists(dump_dir):
            existed_files = 0
            for f in os.listdir(dump_dir):
                if f.startswith(instance.publish.table_name + "."):
                    #the file belongs to the job,remove it
                    os.remove(os.path.join(dump_dir,f))
                else:
                    existed_files += 1

            if not existed_files:
                os.rmdir(dump_dir)


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
