from django import forms

from tablemanager.models import Workspace
from livelayermanager.models import Datasource,Layer,SqlViewLayer
from borg_utils.form_fields import GeoserverSettingForm,MetaTilingFactorField,GridSetField
from borg_utils.form_fields import GroupedModelChoiceField,BorgSelect
from borg_utils.forms import BorgModelForm

class DatasourceForm(BorgModelForm,GeoserverSettingForm):
    """
    A form for Datasource model
    """
    max_connections = forms.IntegerField(label="Max concurrent connections",initial=10,min_value=1,max_value=128)
    max_connections.setting_type = "geoserver_setting"
    max_connections.key = "max connections"

    connect_timeout = forms.IntegerField(label="Connect timeout in seconds",initial=30,min_value=1,max_value=3600)
    connect_timeout.setting_type = "geoserver_setting"
    connect_timeout.key = "Connection timeout"

    min_connections = forms.IntegerField(label="Min concurrent connections",initial=1,min_value=1,max_value=128)
    min_connections.setting_type = "geoserver_setting"
    min_connections.key = "min connections"

    max_connection_idle_time = forms.IntegerField(label="Max connection idle time",initial=300,min_value=1)
    max_connection_idle_time.setting_type = "geoserver_setting"
    max_connection_idle_time.key = "Max connection idle time"

    fetch_size = forms.IntegerField(label="Fetch size",initial=1000,min_value=1)
    fetch_size.setting_type = "geoserver_setting"
    fetch_size.key = "fetch size"


    workspace = GroupedModelChoiceField('publish_channel',queryset=Workspace.objects.all(),required=True,choice_family="workspace",choice_name="workspace_choices",widget=BorgSelect())

    def __init__(self, *args, **kwargs):
        kwargs['initial']=kwargs.get('initial',{})
        self.get_setting_from_model(*args,**kwargs)
        super(DatasourceForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['workspace'].widget.attrs['readonly'] = True

    def _post_clean(self):
        if self.errors:
            return

        self.set_setting_to_model()
        super(DatasourceForm,self)._post_clean()

    class Meta:
        model = Datasource
        fields = "__all__"


class LayerForm(BorgModelForm,GeoserverSettingForm):
    """
    A form for Layer model
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

        super(LayerForm, self).__init__(*args, **kwargs)
        self.fields['table'].widget.attrs['readonly'] = True
        instance = kwargs.get("instance")
        if instance and instance.is_published:
            self.fields['name'].widget.attrs['readonly'] = True

    def _post_clean(self):
        if self.errors:
            return

        self.set_setting_to_model()
        super(LayerForm,self)._post_clean()


    class Meta:
        model = Layer
        fields = "__all__"

class SqlViewLayerForm(BorgModelForm,GeoserverSettingForm):
    """
    A form for SqlViewLayer model
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

        super(SqlViewLayerForm, self).__init__(*args, **kwargs)
        instance = kwargs.get("instance")
        if instance and instance.is_published:
            self.fields['name'].widget.attrs['readonly'] = True

    def _post_clean(self):
        if self.errors:
            return

        self.set_setting_to_model()
        super(SqlViewLayerForm,self)._post_clean()


    class Meta:
        model = SqlViewLayer
        fields = "__all__"

