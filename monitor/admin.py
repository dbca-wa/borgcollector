from django.contrib import admin

from monitor.models import (
    PublishSyncStatus,SlaveServer,TaskSyncStatus
)
from borg.admin import site

class SlaveServerAdmin(admin.ModelAdmin):
    readonly_fields = ("id","name","listen_channels","code_version","last_poll_time","last_sync_time","_last_sync_message","register_time","publish_status","task_status")
    list_display = ("id","name","listen_channels","code_version","last_poll_time","last_sync_time","register_time","publish_status","task_status")
    search_fields = ("name",)

    def _last_sync_message(self,o):
        if o.last_sync_message:
            return "<p style='white-space:pre'>" + o.last_sync_message + "</p>"
        else:
            return ''

    _last_sync_message.allow_tags = True
    _last_sync_message.short_description = "Last Sync Message"

    def publish_status(self,o):
        return "<a href='/monitor/publishsyncstatus/?q={0}'>Status</a>".format(o.name)
    publish_status.allow_tags = True
    publish_status.short_description = "Publish Status"

    def task_status(self,o):
        return "<a href='/monitor/tasksyncstatus/?q={0}'>Status</a>".format(o.name)
    task_status.allow_tags = True
    task_status.short_description = "Task Status"

    def has_add_permission(self,request):
        return False


class PublishSyncStatusAdmin(admin.ModelAdmin):
    readonly_fields = ("id","slave_server","_publish","spatial_type","sync_job_id","sync_job_batch_id","sync_time","_sync_message","deploied_job_id","deploied_job_batch_id","deploy_time","_deploy_message","_preview_file")
    list_display = ("_status","id","slave_server","_publish","spatial_type","deploied_job_id","deploy_time","sync_job_id","sync_time","_preview_file")
    search_fields = ("slave_server__name","publish","deploied_job_id","sync_job_id")
    list_display_links = ("id",)
    list_filter = ("slave_server",)

    def _publish(self,o):
        if o.publish:
            return "<a href='/tablemanager/publish/?q={0}'>{0}</a>".format(o.publish)
        else:
            return ""
    _publish.allow_tags = True
    _publish.short_description = "Publish"

    def _deploy_message(self,o):
        if o.deploy_message:
            return "<p style='white-space:pre'>" + o.deploy_message + "</p>"
        else:
            return ''

    _deploy_message.allow_tags = True
    _deploy_message.short_description = "Deploy Message"

    def _status(self,o):
        return not bool(o.sync_job_id)

    _status.short_description = ""
    _status.boolean = True

    def _preview_file(self,o):
        if o.preview_file:
            return "<img src='{0}'>".format(o.preview_file.url)
        else:
            return ''

    _preview_file.allow_tags = True
    _preview_file.short_description = "Preview"

    def _sync_message(self,o):
        if o.sync_message:
            return "<p style='white-space:pre'>" + o.sync_message + "</p>"
        else:
            return ''

    _sync_message.allow_tags = True
    _sync_message.short_description = "Sync Message"

    def has_add_permission(self,request):
        return False


class TaskSyncStatusAdmin(admin.ModelAdmin):
    list_display = ("id","slave_server","task_type","_task_name","action","sync_succeed","sync_time","_preview_file")
    readonly_fields = ("id","slave_server","task_type","_task_name","action","sync_succeed","sync_time","_sync_message","_preview_file")
    search_fields = ("slave_server__name","task_type","task_name")
    list_filter = ("slave_server",)


    def _preview_file(self,o):
        if o.preview_file:
            return "<img src='{0}'>".format(o.preview_file.url)
        else:
            return ''

    _preview_file.allow_tags = True
    _preview_file.short_description = "Preview"

    def _task_name(self,o):
        if o.task_name:
            if o.task_type == "feature":
                return "<a href='/tablemanager/publish/?q={1}'>{0}:{1}</a>".format(*o.task_name.split(':'))
            elif o.task_type == "wms store":
                return "<a href='/wmsmanager/wmsserver/?q={1}'>{0}:{1}</a>".format(*o.task_name.split(':'))
            elif o.task_type == "wms layer":
                return "<a href='/wmsmanager/interestedwmslayer/?q={1}'>{0}:{1}</a>".format(*o.task_name.split(':'))
            elif o.task_type == "layergroup":
                return "<a href='/layergroup/layergroup/?q={1}'>{0}:{1}</a>".format(*o.task_name.split(':'))
            else:
                return o.task_name
        else:
            return ""

    _task_name.allow_tags = True
    _task_name.short_description = "Task name"

    def _sync_message(self,o):
        if o.sync_message:
            return "<p style='white-space:pre'>" + o.sync_message + "</p>"
        else:
            return ''

    _sync_message.allow_tags = True
    _sync_message.short_description = "Sync Message"

    def has_add_permission(self,request):
        return False

site.register(SlaveServer, SlaveServerAdmin)
site.register(PublishSyncStatus, PublishSyncStatusAdmin)
site.register(TaskSyncStatus, TaskSyncStatusAdmin)
