import os

from django.db import models
from django.utils import timezone
from django.utils.six import with_metaclass

from borg_utils.borg_config import BorgConfiguration

from tablemanager.models import Publish

class UserRoleStatus(object):
    NEW = 'New'
    REMOVE = 'Remove'
    UPDATE = 'Update'
    SYNCED = 'Synced'
    REMOVED = 'Removed'
STATUS_CHOICES = (
    (UserRoleStatus.NEW,UserRoleStatus.NEW),
    (UserRoleStatus.REMOVE,UserRoleStatus.REMOVE),
    (UserRoleStatus.UPDATE,UserRoleStatus.UPDATE),
    (UserRoleStatus.SYNCED,UserRoleStatus.SYNCED),
    (UserRoleStatus.REMOVED,UserRoleStatus.REMOVED),
)
class UserRoleSyncStatus(object):
    NO_NEED = 'N/A'
    SUCCEED = 'Succeed'
    FAILED = 'Failed'
    NOT_CHANGED = 'Not Changed'
    NOT_EXECUTED = 'Not Executed'

class StringListField(with_metaclass(models.SubfieldBase, models.CharField)):
    """
    save a string list to a char field.
    """
    description = "A hand of saving a list value to char field"

    def __init__(self,separator=",", sort=True, *args, **kwargs):
        self.separator = separator
        self.sort = sort
        super(StringListField,self).__init__(*args,**kwargs)

    def deconstruct(self):
        name,path,args,kwargs = super(StringListField,self).deconstruct()
        if self.separator != ",":
            kwargs["separator"] = self.spearator
        if not self.sort:
            kwargs["sort"] = self.sort
        return name,path,args,kwargs

    def to_python(self,value):
        if isinstance(value,list):
            return value
        if value:
            return value.split(self.separator)
        else:
            return None

    def get_prep_value(self,value):
        if value:
            if self.sort:
                value = sorted(value)
            return self.separator.join(value)
        else:
            return None

class Role(models.Model):
    name = models.CharField(max_length=64,null=False,editable=False,primary_key=True)
    status = models.CharField(max_length=16,null=False,editable=False,choices=STATUS_CHOICES)
    last_sync_time = models.DateTimeField(null=True,editable=False)
    last_update_time = models.DateTimeField(null=False,editable=False)

class User(models.Model):
    name = models.CharField(max_length=128,null=False,editable=False,primary_key=True)
    synced_roles = StringListField(max_length=256,null=True,editable=False,sort=False)
    latest_roles = StringListField(max_length=256,null=True,editable=False,sort=False)
    status = models.CharField(max_length=16, null=False, editable=False,choices=STATUS_CHOICES)
    last_sync_time = models.DateTimeField(null=True,editable=False)
    last_update_time = models.DateTimeField(null=False,editable=False)

class SyncLog(models.Model):
    sync_time = models.DateTimeField(null=True,editable=False)
    automatic = models.BooleanField(null=False,editable=False,default=True)
    load_status = models.CharField(max_length=32,null=True,editable=False)
    commit_status = models.CharField(max_length=32,null=True,editable=False)
    push_status = models.CharField(max_length=32,null=True,editable=False)
    message = models.TextField(null=True,editable=False)
    end_time = models.DateTimeField(null=True,editable=False)
    
