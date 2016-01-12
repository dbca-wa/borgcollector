from datetime import timedelta
from django.utils import timezone
import logging

from tablemanager.models import Publish,Input,Normalise
from harvest.models import Job
from harvest.jobstates import Completed

class HarvestJobCleaner(object):
    """
    A cleaner to clean harvest job.
    """
    logger = logging.getLogger(__name__)

    def __init__(self,expire_days,min_jobs):
        self.expire_days = expire_days if  expire_days > 0 else 0
        self.min_jobs = min_jobs if min_jobs > 1 else 1

    def clean(self):
        """
        clean the outdated jobs.
        """
        #import ipdb;ipdb.set_trace()
        #find all publishes which has published at least one time
        outdated_date = None
        if self.expire_days:
            outdated_date = timezone.now() - timedelta(self.expire_days)
            self.logger.info("Begin to clean the jobs finished before {0}, but at least {1} latest successful jobs for each publish will be preserved.".format(outdated_date,self.min_jobs))
        else:
            self.logger.info("Begin to clean all jobs, except {1} latest successful jobs for each publish".format(outdated_date,self.min_jobs))

        deleted_jobs = 0
        for p in Publish.objects.filter(job_id__isnull = False):
            #get the earlist job which should be kept.
            earliest_job = None
            try:
                earliest_job = p.job_set.filter(state=Completed.instance().name,launched__isnull=False).order_by('-finished')[self.min_jobs - 1]    
            except IndexError:
                #the number of existing jobs is less than min_jobs, no need to clean jobs.
                continue
            jobs = p.job_set.filter(pk__lt = earliest_job.pk)
            if self.expire_days:
                #if spefified expire days, only expired jobs will be deleted
                jobs = jobs.filter(finished__lt = outdated_date)

            #find all the publish's jobs and delete it.
            for j in jobs:
                #check whether this job is referenced by Input or Normalise
                if Input.objects.filter(job_id=j.pk).exists() or Normalise.objects.filter(job_id=j.pk).exists():
                    #still referenced by input or normalise, can not delete 
                    continue;
                j.delete()
                deleted_jobs += 1
                self.logger.debug("Delete outdated job({0})".format(j.pk))

        if deleted_jobs == 1:
            self.logger.info("{0} outdated job has been deleted.".format(deleted_jobs))
        elif deleted_jobs > 1:
            self.logger.info("{0} outdated job have been deleted.".format(deleted_jobs))
        else:
            self.logger.info("Not find any outdated jobs.")
