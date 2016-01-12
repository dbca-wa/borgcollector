import os
import traceback
import subprocess
import tempfile
import dj_database_url
from xml.etree import ElementTree
import re
import logging
from xml.dom import minidom

from django.views.generic import View
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator 
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse,HttpResponseBadRequest,HttpResponseServerError
from django.template import Context, Template

from tablemanager.models import ForeignTable

# Create your views here.

logger = logging.getLogger(__name__)

class VRTFileView(View):
    """
    Process vrt file
    """
    http_method_names = ['post']

    fdw_dict = dj_database_url.parse(settings.FDW_URL)

    _field_re = re.compile("[ \t]*(?P<type>[a-zA-Z0-9]+)[ \t]*(\([ \t]*(?P<width>[0-9]+)\.(?P<precision>[0-9]+)\))?[ \t]*")

    _datasource_info_re = re.compile("[(\n)|(\r\n)](?P<key>[a-zA-Z0-9_\-][a-zA-Z0-9_\- ]*[a-zA-Z0-9_\-]?)[ \t]*:(?P<value>[^\r\n]*([(\r\n)|(\n)](([ \t]+[^\r\n]*)|(GEOGCS[^\r\n]*)))*)")
 
    @method_decorator(login_required)
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super(VRTFileView, self).dispatch(*args, **kwargs)

    def post(self,request,*args,**kwargs):
        """
        update vrt file
        """
        action = request.POST.get('action')
        try:
            if not action:
                return HttpResponseBadRequest(reason="Empty action.")
            elif action == "insert_fields":
                return self._insert_fields(request)
            else:
                return HttpResponseBadRequest(reason="Unrecoginzed action({0}).".format(action))
        except Exception as ex:
            logger.error(traceback.format_exc())
            return HttpResponseServerError(reason="{0}:{1}".format(type(ex),ex.message))

    def _get_datasource_info(self,vrt):
        """
        Return datasource info as a list of (key, value) items.
        """
        vrt_file = tempfile.NamedTemporaryFile()
        try:
            vrt_file.write(vrt)
            vrt_file.flush()
            output = subprocess.check_output(["ogrinfo", "-ro", "-al" , "-so", vrt_file.name], stderr=subprocess.STDOUT)
            if output.find("ERROR") > -1:
                logger.error(output)   
                raise Exception(l)
            else:
                if output[0:1] != "\n" and output[0:2] != "\r\n":
                    output = "\n" + output

                result = self._datasource_info_re.findall(output)
                return [(item[0],item[1]) for item in result]
        finally:
            vrt_file.close()

    def _xmltostring(self,element):
        """
        return a pretty formated xml string
        """
        new_vrt = ElementTree.tostring(element,"UTF-8")
        root = minidom.parseString(new_vrt)
        new_vrt = root.toprettyxml(indent="    ")
        return "\n".join([line for line in new_vrt.splitlines() if line.strip()])

    def _insert_fields(self,request):
        """
        Insert all fields of data source into vrt file.
        If some fields are already in the vrt file, these fields will be preserved and only insert the other fields.
        """
        #retrieve the parameters from request
        vrt = request.POST.get('vrt')
        if not vrt:
            return HttpResponseBadRequest(reason="Empty vrt.")

        name = request.POST.get('name')
        if not name:
            return HttpResponseBadRequest(reason="Missing input name.")

        foreign_table_id = request.POST.get('foreign_table')
        if foreign_table_id:
            try:
                foreign_table_id = int(foreign_table_id)
            except:
                return HttpResponseBadRequest(reason="Foreign table identity is not integer.")

        foreign_table = None

        d = {'name':name}
        if foreign_table:
            try:
                foreign_table = ForeignTable.objects.get(pk = foreign_table_id)
            except:
                return HttpResponseBadRequest(reason="Foreign table does not exist")

            d['name'] = foreign_table.name
            d.update(fdw_dict)

        #instantiate vrt template
        vrt = Template(vrt).render(Context({"self": d}))

        root = None
        try:
            root = ElementTree.fromstring(vrt)
        except:
            return HttpResponseBadRequest("Invalid xml format.")
        layer = list(root)[0]
        #find the first non OGRVRTWarpedLayer layer
        while layer.tag == "OGRVRTWarpedLayer":
            layer = layer.find("OGRVRTLayer") or layer.find("OGRVRTUnionLayer") or layer.find("OGRVRTWarpedLayer")

    
        union_layer = None
        if layer.tag == "OGRVRTUnionLayer":
            #currently only support union similiar layers which has same table structure, all fields will be configured in the first layer, 
            union_layer = layer
            layer = list(union_layer)[0]
            while layer.tag == "OGRVRTWarpedLayer":
                layer = layer.find("OGRVRTLayer") or layer.find("OGRVRTUnionLayer") or layer.find("OGRVRTWarpedLayer")

            #currently,only does not support union layer include another union layer .
            if layer.tag == "OGRVRTUnionLayer":
                return HttpResponseBadRequest(reason="Does not support union layer includes another union layer.")

        field_childs = layer.findall("Field") or []

        #remove fields first
        for f in field_childs:
            layer.remove(f)

        if union_layer is not None:
            #remove all fields from union layer
            for f in union_layer.findall("Field") or []:
                union_layer.remove(f)
            #remove all fields from included layers
            for l in list(union_layer):
                while l.tag == "OGRVRTWarpedLayer":
                    l = layer.find("OGRVRTLayer") or layer.find("OGRVRTUnionLayer") or layer.find("OGRVRTWarpedLayer")

                #currently,only does not support union layer include another union layer .
                if l.tag == "OGRVRTUnionLayer":
                    return HttpResponseBadRequest(reason="Does not support union layer includes another union layer.")

                for f in l.findall("Field") or []:
                    l.remove(f)
            #add field strategy into union layer
            field_strategy = union_layer.find("FieldStrategy")
            if field_strategy is not None:
                union_layer.remove(field_strategy)
            #add first layer strategy into union layer
            field_strategy = ElementTree.Element("FieldStrategy")
            setattr(field_strategy,"text","FirstLayer")
            union_layer.append(field_strategy)

        vrt = self._xmltostring(root)
        #get data source information.
        info = None
        try:
            info = self._get_datasource_info(vrt)
        except Exception as ex:
            return HttpResponseBadRequest(reason="{0}:{1}".format(type(ex),ex.message))

        fields = []
        
        for k,v in info:
            if k in ("INFO","Layer name","Geometry","Metadata","Feature Count","Extent","Layer SRS WKT"):
                continue
            if k.find(" ") >= 0:
                #include a emptry, can't be a column
                continue
            m = self._field_re.search(v)
            if m:
                #convert the column name to lower case
                fields.append((k.lower(),m.group('type'),m.group('width'),m.group('precision')))

        #convert the column name into lower case
        for f in field_childs:
            f.set('name',f.get('name').lower())
        field_child_dict = dict(zip([f.get('name') for f in field_childs],field_childs))

        #readd all the fields
        element_attrs = {}
        for f in fields:
            if f[0] in field_child_dict:
                layer.append(field_child_dict[f[0]])
            else:
                element_attrs['name'] = f[0]
                element_attrs['type'] = f[1]

                if f[2] and f[2] != "0":
                    element_attrs['width'] = f[2]
                elif 'width' in element_attrs:
                    del element_attrs['width']

                if f[3] and f[3] != "0":
                    element_attrs['precision'] = f[3]
                elif 'precision' in element_attrs:
                    del element_attrs['precision']

                layer.append(ElementTree.Element("Field",attrib=element_attrs))
    
        return HttpResponse(self._xmltostring(root), content_type="text/plain")







