from django.conf.urls import  include, url
from django.conf import settings
from django.conf.urls.static import static

from borg.admin import site
from filemanager.views import FileDownloadView
import harvest.urls
from borg.api import urlpatterns as apiurlpatterns
urlpatterns = [
    url(r'^', include(site.urls)),
    url(r'^job/', include(harvest.urls)),
    url(r'^download/(?P<path>.*)$', FileDownloadView.as_view(),{"document_root":settings.DOWNLOAD_ROOT}, name = 'file_download' ),
    url(r'^preview/(?P<path>.*)$', FileDownloadView.as_view(),{"document_root":settings.PREVIEW_ROOT}, name = 'layer_preview' ),
    url(r'^api/',include(apiurlpatterns,namespace='api')),
]  + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
