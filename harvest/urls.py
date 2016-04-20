from django.conf.urls import patterns,  url
from harvest.views import ApproveJobView, CancelJobView

urlpatterns = patterns('',
    url(r'^(?P<job_id>\d+)/approve?$', ApproveJobView.as_view(), name = 'approve_job' ),
    url(r'^(?P<job_id>\d+)/cancel?$', CancelJobView.as_view(), name = 'cancel_job' ),

)
