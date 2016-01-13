import json

from restless.dj import DjangoResource
from restless.resources import skip_prepare

from django.conf.urls import patterns,  url


from harvest.models import Job
from harvest.jobstatemachine import JobStatemachine
from borg_utils.jobintervals import Triggered

class JobResource(DjangoResource):
    def is_authenticated(self):
        return self.request.user.is_authenticated()

    @staticmethod
    def urls():
        return patterns('',
            url(r'^/?$',JobResource.as_list(),name='api_job_create'),
        )
     
    @skip_prepare
    def create(self):
        job_batch_id = Triggered.instance().job_batch_id
        resp = {"status":True, "message":{}}
        result = None
        for name in self.data.get('publishes') or []:
            result = JobStatemachine.create_job_by_name(name,Triggered.instance(),job_batch_id)
            if result[0]:
                resp["message"][name] = "job id : {0}".format(result[1])
            else:
                resp["status"] = False
                resp["message"][name] = result[1]

        return resp




        

