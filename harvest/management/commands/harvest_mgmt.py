import time
import logging
import traceback
import atexit
import sys
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from optparse import make_option
from django.core.exceptions import ObjectDoesNotExist

from borg_utils.jobintervals import JobInterval
from harvest.jobstatemachine import JobStatemachine
from harvest.models import Process
from harvest.jobcleaner import HarvestJobCleaner
from harvest.harvest_ds import HarvestDatasource

logger = logging.getLogger(__name__)

class RepeatedJob(object):
    job_batch_id = None
    def __init__(self,interval,options=None):
        self._interval = interval
        self._process = None
        self._options = options
        try:
            p = Process.objects.get(name=self.name)
            if not p.can_run:
                logger.info("The process () is already running on server {} with pid ({})".format(p.name,p.server,p.pid))
                #force to reload process information.
                self._process = None
            elif not p.same_process:
                #update the process info
                p.server = Process.current_server
                p.pid = Process.current_pid
                p.status = "waiting"
                p.save(update_fields=["server","pid","status"])
            else:
                p.status = "waiting"
                p.save(update_fields=["status"])
        except ObjectDoesNotExist:
            p = Process(name=self.name,desc=self.desc,server=Process.current_server,pid=Process.current_pid,status="Init",next_scheduled_time=self._interval.next_scheduled_time())
            p.save()

    @property
    def name(self):
        raise NotImplementedError("Not Implemented")

    @property
    def desc(self):
        raise NotImplementedError("Not Implemented")

    @property
    def last_message(self):
        raise NotImplementedError("Not Implemented")

    def execute(self,time):
        raise NotImplementedError("Not Implemented")

    def run(self,now):
        """
        Try to run the job.
        Return the next scheduled time
        """
        if self._process is None:
            try:
                p = Process.objects.get(name=self.name)
                if not p.can_run:
                    logger.info("The process {} is already running on server {} with pid ({})".format(p.name,p.server,p.pid))
                    #force to reload process information.
                    self._process = None
                    return self._interval.next_scheduled_time()
                elif not p.same_process:
                    #update the process info
                    p.server = Process.current_server
                    p.pid = Process.current_pid
                    p.status = "waiting"
                    p.save(update_fields=["server","pid","status"])
                else:
                    p.status = "waiting"
                    p.save(update_fields=["status"])

            except ObjectDoesNotExist:
                p = Process(name=self.name,desc=self.desc,server=Process.current_server,pid=Process.current_pid,status="Init",next_scheduled_time=self._interval.next_scheduled_time())
                p.save()
            except:
                raise 

        if now < p.next_scheduled_time:
            #before next scheduled time
            #logger.info("No need to run job ({})".format(self.name))
            return p.next_scheduled_time

        #after next scheduled time, begin to run
        p.last_starttime = timezone.now()
        p.last_endtime = None
        p.last_message = None
        p.next_scheduled_time = self._interval.next_scheduled_time()
        p.status = "running"
        p.save(update_fields=["last_starttime","last_endtime","last_message","next_scheduled_time","status"])
        logger.info("Begin to run job ({})".format(self.name))
        is_shutdown = False
        try:
            result = self.execute(now)
            logger.info("End to run job ({})".format(self.name))
            p.status = "waiting"
            if result is not None:
                if isinstance(result,list):
                    is_shutdown = result[0]
                    result = result[1]
                if isinstance(result,tuple):
                    p.last_message = self.last_message.format(*result)
                else:
                    p.last_message = self.last_message.format(result)
            else:
                p.last_message = self.last_message
        except KeyboardInterrupt:
            p.status = "error"
            p.last_message = traceback.format_exc()
            logger.error("Failed to run job ({}).\n{}".format(self.name,p.last_message))
            is_shutdown = True
        except SystemExit:
            p.status = "error"
            p.last_message = traceback.format_exc()
            logger.error("Failed to run job ({}).\n{}".format(self.name,p.last_message))
            is_shutdown = True
        except:
            p.status = "error"
            p.last_message = traceback.format_exc()
            logger.error("Failed to run job ({}).\n{}".format(self.name,p.last_message))

        p.last_endtime = timezone.now()


        logger.info("{} : {}".format(p.name,p.last_message))

        p.next_scheduled_time = self._interval.next_scheduled_time()
        p.save(update_fields=["last_starttime","last_endtime","last_message","next_scheduled_time","status"])

        if is_shutdown:
            sys.exit(1)

        return p.next_scheduled_time

class CreateJob(RepeatedJob):
    @property
    def name(self):
        return "create_{}_job".format(self._interval)

    @property
    def desc(self):
        return "Create {} harvest job".format(self._interval)

    @property
    def last_message(self):
        return "{} harvest jobs created."

    def execute(self,time):
        return JobStatemachine.create_jobs(self._interval,RepeatedJob.job_batch_id)

class HarvestJob(RepeatedJob):
    def __init__(self,interval,options=None):
        self._first_run = True
        super(HarvestJob,self).__init__(interval,options)

    @property
    def name(self):
        return "harvest"

    @property
    def desc(self):
        return "Harvest and publish data"

    @property
    def last_message(self):
        return "{} jobs succeed, {} jobs failed, {} jobs ignored, {} jobs running into error."

    def execute(self,time):
        try:
            return JobStatemachine.run_all_jobs(self._first_run)
        finally:
            self._first_run = False

class CheckDsJob(RepeatedJob):
    @property
    def name(self):
        return "check_datasource"

    @property
    def desc(self):
        return "Monitor the modification status of file system based dataset"

    @property
    def last_message(self):
        return "{} datasources have been changed."

    def execute(self,time):
        return HarvestDatasource(True,0).harvest()

class CleanJob(RepeatedJob):
    @property
    def name(self):
        return "clean_job"

    @property
    def desc(self):
        return "Clean outdate jobs and release disk space."

    @property
    def last_message(self):
        return "{} outdated jobs have been removed.expire_days={}, min_jobs={}".format("{}",self._options["expire_days"],self._options["min_jobs"])

    def execute(self,time):
        return HarvestJobCleaner(self._options["expire_days"],self._options["min_jobs"]).clean()

@atexit.register
def shutdown():
        Process.objects.filter(server=Process.current_server,pid=Process.current_pid).update(status="shutdown")
        logger.info("Harvest management process exit.server={}, pid={}".format(Process.current_server,Process.current_pid))

class Command(BaseCommand):
    help = 'Create harvest job'
    option_list = BaseCommand.option_list + (
        make_option(
            '-c',
            '--create-job',
            action='store_true',
            dest='create_job',
            help='Enable creating harvest job feature.'
        ),

        make_option(
            '-r',
            '--run-job',
            action='store_true',
            dest='run_job',
            help='Enable running harvest job feature.'
        ),

        make_option(
            '--check-ds',
            action='store_true',
            dest='check_ds',
            default=None,
            help='Enable checking datasource feature'
        ),

        make_option(
            '--clean-job-now',
            action='store_true',
            dest='clean_job_now',
            default=None,
            help='Cleaning outdated job immediately'
        ),

        make_option(
            '--clean-job',
            action='store_true',
            dest='clean_job',
            default=None,
            help='Enable cleaning outdated job feature'
        ),
        make_option(
            '--expire-days',
            action='store',
            dest='expire_days',
            help='The expire days of a job after publish time; default is 90'
        ),
        make_option(
            '--min-jobs',
            action='store',
            dest='min_jobs',
            help='The specified number of successful jobs should be kept in the system for each publish; default is 1'
        ),
    )

    def handle(self, *args, **options):
        jobs = []

        #add all create jobs
        if options["create_job"]:
            for interval in JobInterval.publish_intervals():
                if interval in [JobInterval.Manually, JobInterval.Realtime, JobInterval.Triggered]:
                    continue
                jobs.append(CreateJob(interval))

        #add run jobs;
        if options["run_job"]:
            jobs.append(HarvestJob(JobInterval.Minutely))

        #check datasource
        if options["check_ds"]:
            jobs.append(CheckDsJob(JobInterval.Hourly))

        #clean outdated jobs
        if options["clean_job"] or options["clean_job_now"]:
            if options['expire_days']:
                try:
                    options['expire_days'] = int(options['expire_days'])
                    if options['expire_days'] <= 0:
                        options['expire_days'] = 90
                except:
                    options['expire_days'] = 90
            else:
                options['expire_days'] = 90

            if options['min_jobs']:
                try:
                    options['min_jobs'] = int(options['min_jobs'])
                    if options['min_jobs'] <= 0:
                        options['min_jobs'] = 1
                except:
                    options['min_jobs'] = 1
            else:
                options['min_jobs'] = 1

            if options["clean_job_now"]:
                HarvestJobCleaner(options["expire_days"],options["min_jobs"]).clean()

            if options["clean_job"]:
                jobs.append(CleanJob(JobInterval.Daily,options))

        if not jobs:
            #no repeated jobs to run
            return

        #begin to run jobs
        next_run_time = None
        min_next_run_time = None
        now = None
        while(True):
            min_next_run_time = None
            now = timezone.now()
            RepeatedJob.job_batch_id = JobInterval.Daily.job_batch_id(now)
            for job in jobs:
                next_run_time = job.run(now)
                if min_next_run_time:
                    min_next_run_time = next_run_time if next_run_time < min_next_run_time else min_next_run_time
                else:
                    min_next_run_time = next_run_time

            sleep_times = (min_next_run_time - timezone.now()).total_seconds()
            if sleep_times > 0:
                logger.info("sleep until {}".format(timezone.localtime(min_next_run_time)))
                time.sleep(sleep_times)

