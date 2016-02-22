import logging
import json
from datetime import timedelta,datetime
import time

from django.db import transaction,models
from django.utils import timezone
from django.conf import settings
from django.core.files import File

from tablemanager.models import Publish, Workspace
from harvest.models import Job,JobLog
from harvest.jobstates import JobStateOutcome,Failed,Completed,JobState
from harvest.harveststates import Waiting
from borg_utils.jobintervals import JobInterval,Manually,Realtime
from borg_utils.borg_config import BorgConfiguration

logger = logging.getLogger(__name__)

class JobStatemachine(object):
    @staticmethod
    def create_job_by_name(publish_name,job_interval=Manually.instance(),job_batch_id=None):
        """
        manually create a job by name
        """
        components = publish_name.split('.', 1)
        p  = None
        try:
            if len(components) == 2:
                w = Workspace.objects.get(name=components[0])
                p = Publish.objects.get(name=components[1], workspace=w)
            else:
                p = Publish.objects.get(name=publish_name)
        except:
            return (False,"Not exist")
        return JobStatemachine._create_job(p,job_interval,job_batch_id)


    @staticmethod
    def create_job(publish_id,job_interval=Manually.instance(),job_batch_id=None):
        """
        manually create a job by id
        """
        p = None
        try:
            p = Publish.objects.get(pk=publish_id)
        except:
            return (False,"Not exist")
        return JobStatemachine._create_job(p,job_interval,job_batch_id)

    @staticmethod
    def _create_job(publish,job_interval=Manually.instance(),job_batch_id=None):
        """
        manually create a job
        return (true,'OK'), if create a job, otherwise return (False,message)
        """
        if not publish.publish_status.publish_enabled:
            #publish is disabled, ignore
            return (False,"Disabled")

        if publish.waiting > 0:
            #already have one waiting harvest job, create another is meanless.
            return (False,"Already have a waiting job")

        if not job_batch_id:
            job_batch_id = Manually.instance().job_batch_id

        job = None
        with transaction.atomic():
            if publish.waiting > 0:
                #already have one waiting harvest job, create another is meanless.
                return;

            publish.waiting = models.F("waiting") + 1
            job = Job(
                        batch_id = job_batch_id,
                        publish = publish,
                        state = Waiting.instance().name,
                        previous_state = None,
                        message = None,
                        created = timezone.now(),
                        launched = None,
                        finished = None,
                        job_type = job_interval.name
                    )
            publish.save(update_fields=['waiting'])
            job.save()
            #add log
            log = JobLog(
                        job_id = job.id,
                        state = "Create",
                        outcome = "Create",
                        message = "Created by custodian" if job_interval == Manually.instance() else "Created by other application",
                        next_state = job.state,
                        start_time = timezone.now(),
                        end_time = timezone.now())
            log.save()

        return (True,job.id)

    @staticmethod
    def create_jobs(interval_choice,job_batch_id=None):
        """
        create the jobs based on publish status
        All jobs will be sorted agaist with publish.priority
        """
        job = None
        log = None
        jobs = []
        job_batch_id = job_batch_id or interval_choice.job_batch_id()

        check_job = Job(id=-1,batch_id="CK" + job_batch_id) if interval_choice == Realtime.instance() else None
        up_to_date = False
        
        for p in Publish.objects.filter(interval = interval_choice.name, waiting = 0).order_by('priority'):
            if not p.publish_status.publish_enabled:
                #publish is disabled, ignore
                continue

            if interval_choice == Realtime.instance():
                #Realtime publish, check whether input is up to date.
                up_to_date = True
                for i in p.inputs:
                    if not i.is_up_to_date(check_job,False):
                        #input is not up to date, clear importing info to avoid double check for foreign table.
                        up_to_date = False
                        break
                if up_to_date:
                    continue

            p.waiting = models.F("waiting") + 1
            job = Job(
                        batch_id = job_batch_id,
                        publish = p,
                        state = Waiting.instance().name,
                        previous_state = None,
                        message = None,
                        created = timezone.now(),
                        launched = None,
                        finished = None,
                        job_type = interval_choice.name
                    )

            #add log
            log = JobLog(
                        state = "Create",
                        outcome = "Create",
                        message = "Create by {0} cron job".format(interval_choice),
                        next_state = job.state,
                        start_time = timezone.now(),
                        end_time = timezone.now())

            jobs.append((p,job,log))

        with transaction.atomic():
            for p,job,log in jobs:
                p.save(update_fields=['waiting'])
                job.save()
                log.job_id = job.id
                log.save()

        return len(jobs)


    @staticmethod
    def send_user_action(job_id,job_state,user_action):
        """
        request a user action
        """

        if not user_action:
            raise Exception("User action is missing")

        job = Job.objects.get(pk = job_id)
        #check whether user action is valid
        current_state = JobState.get_jobstate(job.state)
        if not current_state.outcome_cls.is_manual_outcome(user_action):
            raise Exception("The action '{0}' is not a valid user action.".format(user_action))

        required_state_name = JobState.get_jobstate(job_state).name if job_state else None
        #if action is not a cancel action, job state should be equal with the requested state.
        if user_action == JobStateOutcome.cancelled_by_custodian or (job.state and job.state == required_state_name):
            job.user_action = user_action
            job.save(update_fields=["user_action"])
        else:
            raise Exception("Job is on the state {0} instead of required state {1}".format(job.state, required_state_name))

    @staticmethod
    def run_all_jobs(first_run=True):
        """
        run all jobs sequentially
        """
        succeed_jobs = 0
        failed_jobs = 0
        ignored_jobs = 0
        error_jobs = 0
        for j in Job.objects.exclude(state__in = [Failed.instance().name,Completed.instance().name]).order_by('id'):
            try:
                JobStatemachine.run(j,first_run)
                if j.state == "Completed":
                    if j.launched is None:
                        ignored_jobs += 1
                    else:
                        succeed_jobs += 1
                elif j.state == "Failed":
                    failed_jobs += 1
                else:
                    error_jobs += 1
            except:
                logger.error("job(id={0},name={1}) runs into a exception{2}".format(j.id,j.publish.name,JobState.get_exception_message()))
                error_jobs += 1

        return (succeed_jobs,failed_jobs,ignored_jobs,error_jobs)

    @staticmethod
    def run_job(job_id,step=False):
        JobStatemachine.run(Job.objects.get(pk=job_id),True,step)

    @staticmethod
    def run(job,first_run=True,step=False):
        current_state = JobState.get_jobstate(job.state)

        previous_state = None
        if job.previous_state:
            previous_state = JobState.get_jobstate(job.previous_state)

        log = None
        while True:
            start_time = timezone.now()
            logger.debug("job(id={0},name={1}) begins to execute state ({2})".format(job.id,job.publish.name,job.state))
            if current_state.is_end_state:
                #current job is already finished.
                logger.debug("job(id={0},name={1},state={2}) is finished".format(job.id,job.publish.name,job.state))
                return
            elif job.user_action and ((job.user_action == JobStateOutcome.cancelled_by_custodian and current_state.cancellable) or (job.user_action != JobStateOutcome.cancelled_by_custodian)):
                #have a pending user action.
                if not current_state.outcome_cls.is_manual_outcome(job.user_action):
                    #a invalid user action
                    next_state = current_state
                    state_result = (JobStateOutcome.internal_error, "The action '{0}' is not a valid user action.".format(job.user_action))
                else:
                    try:
                        next_state = current_state.next_state(job.user_action)
                        state_result = (job.user_action,job.user_action)
                        #user action is processed, clear it
                        job.user_action = None
                    except:
                        #can not apply the user action on the current state, stay in the same state
                        next_state = current_state
                        state_result = (JobStateOutcome.internal_error, "The action '{0}' can not apply on the current state({1}).".format(job.user_action,current_state.name))
            elif current_state.is_interactive_state:
                #job is at interactive state, but no user action is requested, return and wait user action.
                return
            elif current_state.is_error_state:
                #wait the configured interval before continue
                try:
                    if not first_run and job.last_execution_end_time and timezone.now() < job.last_execution_end_time + timedelta(seconds=BorgConfiguration.RETRY_INTERVAL):
                        #early than the next execution time. can not run this time
                        return
                    else:
                        state_result = current_state.execute(job,previous_state)
                except:
                    #can not find the last execution time. run it
                    state_result = current_state.execute(job,previous_state)
                next_state = current_state.next_state(state_result[0])
            else:
                try:
                    #normal state without pending user action
                    state_result = current_state.execute(job,previous_state)
                    if not state_result:
                        raise Exception("The outcome of state '{0}' is null.".format(current_state.name))
                except:
                    #run into a unexpected exception
                    state_result = (JobStateOutcome.internal_error, JobState.get_exception_message())

                try:
                    next_state = current_state.next_state(state_result[0])
                except:
                    #can not find a transition from the current state with the state_result, stay at the current state.
                    next_state = current_state
                    if state_result[1]:
                        state_result = (state_result[0],"{0}\n=======================\n{1}".format(JobState.get_exception_message(),state_result[1]))
                    else:
                        state_result = (state_result[0],JobState.get_exception_message())
            end_time = timezone.now()

            logger.debug("job(id={0},name={1}) ends to execute state ({2}) with result ({3});".format(job.id,job.publish.name,job.state,state_result))

            #set the retry times
            if current_state == next_state:
                #stay at the same state, runs into some exception
                job.retry_times += 1
            elif current_state.is_interactive_state:
                #current state is interactive state.
                job.retry_times = 0
            elif current_state.is_error_state:
                #current state is a error state
                if next_state.is_error_state:
                    #stay at the same state, run into a exception
                    job.retry_times += 1
                elif isinstance(next_state,current_state._normal_state):
                    #a normal transition from current state to its associated normal state
                    pass
                else:
                    #a transition from current state to other normal state, reset retry_times.
                    job.retry_times = 0
            elif next_state.is_end_state :
                #reach the end state or a volative state
                job.retry_times = 0
            else:
                #current state is a normal state
                if not next_state.is_error_state:
                    #a successful transition from a normal state to another normal state.
                    job.retry_times = 0
                else:
                    #a failed transition from a normal state to a failed state
                    job.retry_times += 1

            log = JobLog(
                        job_id = job.id,
                        state = job.state,
                        outcome = state_result[0],
                        message = state_result[1],
                        next_state = next_state,
                        start_time = start_time,
                        end_time = end_time)

            if current_state.is_error_state and not current_state.is_interactive_state and not job.user_action and isinstance(next_state,current_state._normal_state):
                #normal transition from error state to normal state, ignore the log
                log = None
            elif next_state.is_error_state or current_state == next_state:
                #failed,
                last_log = JobLog.objects.filter(job_id = job.id).order_by("-pk").first()
                if last_log and last_log.state == job.state and last_log.outcome == state_result[0] and last_log.message == state_result[1] and last_log.next_state == next_state.name:
                    #same execption occur
                    last_log.start_time = start_time
                    last_log.end_time = end_time
                    log = last_log

            if current_state != next_state:
                #job move to a new state, change the job state
                job.previous_state = job.state
                job.state = next_state.name
            else:
                #some bad thing happens,job stays at the same state, leave the job's state untouched
                pass

            job.last_execution_end_time = timezone.now()
            job.message = state_result[1]
            json_data = json.dumps(job.metadict)
            if job.metadata:
                json_data = json.dumps(job.metadict)
                if job.metadata == json_data:
                    job.save(update_fields=['previous_state','state','message','retry_times','last_execution_end_time','user_action'])
                else:
                    job.metadata = json_data
                    job.save(update_fields=['previous_state','state','message','retry_times','last_execution_end_time','user_action','metadata'])
            elif job.metadict:
                job.metadata = json.dumps(job.metadict)
                job.save(update_fields=['previous_state','state','message','retry_times','last_execution_end_time','user_action','metadata'])
            else
                job.save(update_fields=['previous_state','state','message','retry_times','last_execution_end_time','user_action'])

            if log:
                log.save()

            #import ipdb; ipdb.set_trace()
            if current_state == next_state:
                #stay in the same state, stop execution
                logger.debug("job(id={0},name={1},state={2}) stay in the same state.".format(job.id,job.publish.name,job.state))
                return
            elif next_state.is_error_state:
                return
            elif step:
                return

            #set previous_state to the current state, current_state to the next_state
            previous_state = current_state
            current_state = next_state

