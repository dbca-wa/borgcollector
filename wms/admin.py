from reversion import VersionAdmin

from borg.admin import site
from wms.models import WMSLayer, WMSLayerGroup, WMSSource

class WMSSourceAdmin(VersionAdmin):
    pass

class WMSLayerGroupAdmin(VersionAdmin):
    pass

class WMSLayerAdmin(VersionAdmin):
    pass

site.register(WMSSource, WMSSourceAdmin)
site.register(WMSLayerGroup, WMSLayerGroupAdmin)
site.register(WMSLayer, WMSLayerAdmin)
