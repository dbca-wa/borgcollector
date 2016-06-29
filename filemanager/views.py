import os
import mimetypes

from django.http import Http404
from django.shortcuts import render
from django.conf import settings
from django.views.generic import View
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator 
from django.http import HttpResponse

from wsgiref.util import FileWrapper

# Create your views here.

class FileDownloadView(View):
    """
    Process http download request
    """
    http_method_names = ['get']

    @method_decorator(login_required)
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super(FileDownloadView, self).dispatch(*args, **kwargs)

    def get(self,request,path,document_root = getattr(settings,"DOWNLOAD_ROOT")):
        """
        download the file
        """
        #import ipdb;ipdb.set_trace()
        file_name = os.path.join(document_root,path)
        if os.path.exists(file_name):
            mime_type = mimetypes.guess_type(file_name)
            response = HttpResponse(FileWrapper(open(file_name)),content_type=mime_type)
            response["Content-Disposition"] = 'attachment; filename="{0}"'.format(os.path.split(file_name)[1])
            file_size = os.path.getsize(file_name)
            response["Content-Length"] = file_size
            return response
        else:
            raise Http404


