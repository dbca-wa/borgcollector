from django.db import models

from tablemanager.models import Workspace



class WMSSource(models.Model):
    """
    WMS endpoint for accessing remote layers
    """
    workspace = models.ForeignKey(Workspace)
    name = models.CharField(max_length=255, blank=False)
    url = models.CharField(max_length=1024, blank=False)
    username = models.CharField(max_length=255, blank=True)
    password = models.CharField(max_length=255, blank=True)


    def __str__(self):
        return '{}:{}'.format(self.workspace, self.name)


class WMSLayer(models.Model):
    """
    Single remote layer accessed via WMS
    """
    source = models.ForeignKey(WMSSource)
    layer_id = models.CharField(max_length=255, blank=False)
    name = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=1024, blank=True)
    abstract = models.TextField(blank=True)
    applications = models.TextField(blank=True, null=True, editable=False)

    def __str__(self):
        if self.name:
            return '{}:{}'.format(self.source.workspace, self.name)
        else:
            return '{}:{}'.format(self.source.workspace, self.layer_id)
    

class WMSLayerGroup(models.Model):
    """
    A group of WMS layers unioned together
    """
    workspace = models.ForeignKey(Workspace)
    name = models.CharField(max_length=255, blank=False)
    title = models.CharField(max_length=1024, blank=True)
    abstract = models.TextField(blank=True)
    applications = models.TextField(blank=True, null=True, editable=False)

    layers = models.ManyToManyField(WMSLayer)

    def __str__(self):
        return '{}:{}'.format(self.workspace, self.name)
