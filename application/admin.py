from reversion import VersionAdmin

from borg.admin import site
from application.models import Application, Application_Layers
from application.forms import ApplicationForm, Application_LayersForm


class ApplicationAdmin(VersionAdmin):
    list_display = ("name", "description")
    #actions = [instantiate]
    search_fields = ["name"]

    form = ApplicationForm


class Application_LayersAdmin(VersionAdmin):
    list_display = ("application", "_publish", "_wmslayer", "order")
    #actions = [instantiate]
    search_fields = ["application__name", "publish__name", "wmslayer__name"]

    form = Application_LayersForm

    ordering = ['application', 'order', 'publish__name', 'wmslayer__name']

    def _publish(self, o):
        if o.publish:
            return "<a href='/tablemanager/publish/{0}/'>{1}</a>".format(
                o.publish.pk, o.publish.name)
        else:
            return ""
    _publish.allow_tags = True
    _publish.short_description = "Publish"

    def _wmslayer(self, o):
        if o.wmslayer:
            return "<a href='/wmsmanager/wmslayer/{0}/'>{1}</a>".format(
                o.wmslayer.pk, o.wmslayer.name)
        else:
            return ""
    _wmslayer.allow_tags = True
    _wmslayer.short_description = "WMS Layer"

site.register(Application, ApplicationAdmin)
site.register(Application_Layers, Application_LayersAdmin)
