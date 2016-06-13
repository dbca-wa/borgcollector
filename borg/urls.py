from django.conf.urls import patterns, include, url
from django.conf import settings
from django.conf.urls.static import static

from borg.admin import site
from filemanager.views import FileDownloadView
import harvest.urls
from harvest.jobresource import JobResource,MetaResource,MudmapResource

urlpatterns = patterns('',
    url(r'^', include(site.urls)),
    url(r'^job/', include(harvest.urls)),
    url(r'^download/(?P<path>.*)$', FileDownloadView.as_view(),{"document_root":settings.DOWNLOAD_ROOT}, name = 'file_download' ),
    url(r'^preview/(?P<path>.*)$', FileDownloadView.as_view(),{"document_root":settings.PREVIEW_ROOT}, name = 'layer_preview' ),
    url(r'^api/jobs/',include(JobResource.urls(),namespace='job_rest_api')),
    url(r'^api/metajobs/',include(MetaResource.urls(),namespace='meta_rest_api')),
    url(r'^api/mudmap/',include(MudmapResource.urls(),namespace='mudmap_rest_api'))
)  + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
