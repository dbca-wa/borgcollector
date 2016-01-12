from django.shortcuts import render,redirect
from django.views.generic import View
from django.utils.decorators import method_decorator 
from django.contrib.auth.decorators import login_required

from harvest.models import Job
from tablemanager.models import Publish
from harvest.jobstatemachine import JobStatemachine
from harvest.jobstates import JobStateOutcome

# Create your views here.

def cron(request):
    # Should go through all completed jobs unique on table, and for all expired append to todo list
    # Then should add all publishes that have never had a completed job
    # Then should process each publish group in priority order
    lastrun = Job.objects.filter(state = 4).order_by("-launched").distinct("publish")
    todo = []
    for job in lastrun:
        if (timezone.now() - job.launched > timedelta(hours=job.publish.interval)):
            todo.append(job.publish)

    for table in Publish.objects.exclude(job__completed = 4).filter(id__not_in = todo):
        todo.append(job.publish)
    
    return render("cron.html")


def job(request, publish):
    # Should launch a job for a given published table
    pass

class ApproveJobView(View):
    """
    approve job 
    """
    http_method_names = ['get']

    def __init__(self):
        """
        load settings from djago.conf.settings
        """
        pass

    @method_decorator(login_required)
    def get(self,request,job_id):
        """
        approve job
        """
        job_state = request.GET['job_state']
        JobStatemachine.send_user_action(job_id,job_state,JobStateOutcome.approved_by_custodian)
        return redirect("/harvest/runningjob")


class CancelJobView(View):
    """
    cancel job 
    """
    http_method_names = ['get']

    def __init__(self):
        """
        load settings from djago.conf.settings
        """
        pass

    @method_decorator(login_required)
    def get(self,request,job_id):
        """
        cancel job
        """
        #import ipdb;ipdb.set_trace()
        job_state = request.GET['job_state']
        JobStatemachine.send_user_action(job_id,job_state,JobStateOutcome.cancelled_by_custodian)
        return redirect("/harvest/runningjob")

