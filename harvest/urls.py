from django.conf.urls import url
from harvest.views import ApproveJobView, CancelJobView

urlpatterns = (
    url(r'^(?P<job_id>\d+)/approve?$', ApproveJobView.as_view(), name = 'approve_job' ),
    url(r'^(?P<job_id>\d+)/cancel?$', CancelJobView.as_view(), name = 'cancel_job' ),

)
