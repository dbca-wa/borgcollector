from django import forms

from tablemanager.models import Workspace
from wmsmanager.models import WmsServer,WmsLayer
from borg_utils.form_fields import GeoserverSettingForm,MetaTilingFactorField,GridSetField
from borg_utils.form_fields import GroupedModelChoiceField,BorgSelect

class WmsServerForm(forms.ModelForm,GeoserverSettingForm):
    """
    A form for WmsServer model
    """
    max_connections = forms.IntegerField(label="Max concurrent connections",initial=6,min_value=1,max_value=128)
    max_connections.setting_type = "geoserver_setting"
    max_connections.key = "max_connections"


    connect_timeout = forms.IntegerField(label="Connect timeout in seconds",initial=30,min_value=1,max_value=3600)
    connect_timeout.setting_type = "geoserver_setting"
    connect_timeout.key = "connect_timeout"

    read_timeout = forms.IntegerField(label="Read timeout in seconds",initial=60,min_value=1,max_value=3600)
    read_timeout.setting_type = "geoserver_setting"
    read_timeout.key = "read_timeout"


    workspace = GroupedModelChoiceField('publish_channel',queryset=Workspace.objects.all(),required=True,choice_family="workspace",choice_name="workspace_choices",widget=BorgSelect())

    def __init__(self, *args, **kwargs):
        kwargs['initial']=kwargs.get('initial',{})
        self.get_setting_from_model(*args,**kwargs)
        super(WmsServerForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['name'].widget.attrs['readonly'] = True

            self.fields['workspace'].widget.attrs['readonly'] = True

    def _post_clean(self):
        if self.errors:
            return

        self.set_setting_to_model()
        super(WmsServerForm,self)._post_clean()

    class Meta:
        model = WmsServer
        fields = "__all__"


class WmsLayerForm(forms.ModelForm,GeoserverSettingForm):
    """
    A form for WmsLayer model
    """
    create_cache_layer = forms.BooleanField(required=False,label="create_cache_layer",initial={"enabled":True})
    create_cache_layer.setting_type = "geoserver_setting"

    server_cache_expire = forms.IntegerField(label="server_cache_expire",min_value=0,required=False,initial=0,help_text="Expire server cache after n seconds (set to 0 to use source setting)")
    server_cache_expire.setting_type = "geoserver_setting"

    client_cache_expire = forms.IntegerField(label="client_cache_expire",min_value=0,required=False,initial=0,help_text="Expire client cache after n seconds (set to 0 to use source setting)")
    client_cache_expire.setting_type = "geoserver_setting"

    def __init__(self, *args, **kwargs):
        kwargs['initial']=kwargs.get('initial',{})
        self.get_setting_from_model(*args,**kwargs)

        super(WmsLayerForm, self).__init__(*args, **kwargs)
        self.fields['name'].widget.attrs['readonly'] = True
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            if kwargs['instance'].is_published:
                self.fields['kmi_name'].widget.attrs['readonly'] = True
            else:
                if "readonly" in self.fields['kmi_name'].widget.attrs:
                    del self.fields['kmi_name'].widget.attrs['readonly']

    def _post_clean(self):
        if self.errors:
            return

        self.set_setting_to_model()
        super(WmsLayerForm,self)._post_clean()


    class Meta:
        model = WmsLayer
        fields = "__all__"

