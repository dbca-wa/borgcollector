from django.contrib import admin

from harvest.models import (
    Job, JobLog,Process
)
from borg.admin import site
from harvest.jobstates import JobState,JobStateOutcome,Failed,Completed
from harvest.harveststates import Waiting


def harvest(modeladmin, request, queryset):
    for output in queryset:
        output.harvest()
harvest.short_description = "Harvest and update selected outputs"

class JobAdmin(admin.ModelAdmin):
    readonly_fields = ("id","batch_id","_publish","job_type", "state","job_action" ,"previous_state", "_message","retry_times","last_execution_end_time", "created", "launched", "finished","sync_status","job_logs")
    list_display = ("id","batch_id", "_publish","job_type", "state", "created", "launched", "finished","job_action","sync_status","job_logs")
    search_fields = ["publish__name","batch_id","id"]
    actions = None

    def _message(self,o):
        if o.message:
            return "<p style='white-space:pre'>" + o.message + "</p>"
        else:
            return ''

    _message.allow_tags = True
    _message.short_description = "Message"

    def job_action(self,o):
        job_state = JobState.get_jobstate(o.state);
        if not job_state or job_state.is_end_state:
            return ""
        value = "";
        if job_state.is_interactive_state :
            if o.user_action and o.user_action == JobStateOutcome.approved_by_custodian:
                value = "Approved"
            elif not o.user_action or o.user_action != JobStateOutcome.cancelled_by_custodian:
                value = "<a href='/job/" + str(o.id) +"/approve?job_state=" + o.state + "'>Approve</a>"
        if job_state.cancellable:
            if o.user_action and o.user_action == JobStateOutcome.cancelled_by_custodian:
                if value:
                    value += " | Cancelled"
                else:
                    value = "Cancelled"
            else:
                if value:
                    value += " | <a href='/job/" + str(o.id) +"/cancel?job_state=" + o.state + "'>Cancel</a>"
                else:
                    value = "<a href='/job/" + str(o.id) +"/cancel?job_state=" + o.state + "'>Cancel</a>"

        return value

    job_action.short_description = "action"
    job_action.allow_tags = True

    def _publish(self,o):
        if o.publish:
            return str(o.publish)
        else:
            return ""
    _publish.short_description = "Publish"
    _publish.admin_order_field = "publish__name"


    def job_logs(self,o):
        return "<a href='/harvest/joblog/?q={0}'>Logs</a>".format(o.id)
    job_logs.allow_tags = True
    job_logs.short_description = "Logs"

    def sync_status(self,o):
        if o.state == Completed.instance().name and o.launched:
            return "<a href='/monitor/publishsyncstatus/?q={0}'>Sync status</a>".format(o.id)
        else:
            return ""
    sync_status.allow_tags = True
    sync_status.short_description = "Sync Status"

    def has_add_permission(self,request):
        return False

    def has_delete_permission(self,request,obj=None):
        return False

    class Media:
        js = ('/static/js/admin-model-readonly.js',)

class FailingJobAdmin(JobAdmin):
    def get_queryset(self,request):
        qs = super(FailingJobAdmin,self).get_queryset(request)
        return qs.filter(state__in = JobState.all_failed_class_names)

class FailingJob(Job):
    class Meta:
        proxy = True
        verbose_name="Job (Failing)"
        verbose_name_plural="Jobs (Failing)"

class RunningJobAdmin(JobAdmin):
    def get_queryset(self,request):
        qs = super(RunningJobAdmin,self).get_queryset(request)
        return qs.exclude(state__in = [Failed.instance().name,Completed.instance().name])

class RunningJob(Job):
    class Meta:
        proxy = True
        verbose_name="Job (Running)"
        verbose_name_plural="Jobs (Running)"

class EffectiveJobAdmin(JobAdmin):
    def get_queryset(self,request):
        qs = super(EffectiveJobAdmin,self).get_queryset(request)
        return qs.exclude(state__in = [Failed.instance().name,Completed.instance().name],launched=None)

class EffectiveJob(Job):
    class Meta:
        proxy = True
        verbose_name="Job (Effective)"
        verbose_name_plural="Jobs (Effective)"

class JobLogAdmin(admin.ModelAdmin):
    readonly_fields = ("id","_job", "state", "outcome", "_message", "next_state", "start_time", "end_time")
    list_display = ("id","_job","state", "outcome", "_message", "start_time", "end_time")
    search_fields = ["job_id"]

    actions = None

    def _message(self,o):
        if o.message:
            return "<p style='white-space:pre'>" + o.message + "</p>"
        else:
            return ''

    _message.allow_tags = True
    _message.short_description = "Message"
    _message.admin_order_field = "message"

    def _job(self,o):
        if o.job:
            return "<a href='/harvest/job/{}/'>{}</a>".format(o.job.pk,o.job.pk)
        else:
            return ''
    _job.short_description = "Job"
    _job.admin_order_field = "job__pk"
    _job.allow_tags = True

    def has_add_permission(self,request):
        return False

    def has_delete_permission(self,request,obj=None):
        return False

    def get_search_results(self,request,queryset,search_term):
        try:
            #import ipdb; ipdb.set_trace()
            job_id = int(search_term)
            return self.model.objects.filter(job_id = job_id).order_by("start_time"),False
        except:
            if search_term:
                return (self.model.objects.none(),False)
            else:
                return super(JobLogAdmin,self).get_search_results(request,queryset,search_term)


    class Media:
        js = ('/static/js/admin-model-readonly.js',)

class ProcessAdmin(admin.ModelAdmin):
    readonly_fields = ("id","name","desc","server","pid","status","next_scheduled_time","last_starttime","last_endtime","_last_message")
    list_display = ("id","name","server","pid","status","next_scheduled_time","last_starttime","last_endtime","last_message")
    search_fields = ["job_id"]
    actions = None

    def _last_message(self,o):
        if o.message:
            return "<p style='white-space:pre'>" + o.last_message + "</p>"
        else:
            return ''

    _last_message.allow_tags = True
    _last_message.short_description = "Message"

    def has_add_permission(self,request):
        return False

    def has_delete_permission(self,request,obj=None):
        return False

    class Media:
        js = ('/static/js/admin-model-readonly.js',)

site.register(Job, JobAdmin)
#site.register(FailingJob, FailingJobAdmin)
site.register(RunningJob, RunningJobAdmin)
site.register(EffectiveJob, EffectiveJobAdmin)
site.register(JobLog, JobLogAdmin)
site.register(Process, ProcessAdmin)
