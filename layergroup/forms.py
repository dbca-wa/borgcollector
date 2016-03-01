from django import forms

from wmsmanager.models import WmsLayer
from layergroup.models import LayerGroup,LayerGroupLayers
from tablemanager.models import Publish,Workspace
from borg_utils.form_fields import GeoserverSettingForm,MetaTilingFactorField,GridSetField
from borg_utils.form_fields import GroupedModelChoiceField,BorgSelect
from borg_utils.resource_status import ResourceStatus

class LayerGroupForm(forms.ModelForm,GeoserverSettingForm):
    """
    A form for LayerGroup Model
    """
    create_cache_layer = forms.BooleanField(required=False,label="create_cache_layer", initial={"enabled":True})
    create_cache_layer.setting_type = "geoserver_setting"

    server_cache_expire = forms.IntegerField(label="server_cache_expire",min_value=0,required=False,initial=0,help_text="Expire server cache after n seconds (set to 0 to use source setting)")
    server_cache_expire.setting_type = "geoserver_setting"

    client_cache_expire = forms.IntegerField(label="client_cache_expire",min_value=0,required=False,initial=0,help_text="Expire client cache after n seconds (set to 0 to use source setting)")
    client_cache_expire.setting_type = "geoserver_setting"

    workspace = GroupedModelChoiceField('publish_channel',queryset=Workspace.objects.all(),required=True,choice_family="workspace",choice_name="workspace_choices",widget=BorgSelect())

    def __init__(self, *args, **kwargs):
        kwargs['initial']=kwargs.get('initial',{})
        self.get_setting_from_model(*args,**kwargs)

        super(LayerGroupForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['name'].widget.attrs['readonly'] = True
            self.fields['workspace'].widget.attrs['readonly'] = True

    def _post_clean(self):
        if self.errors:
            return

        self.set_setting_to_model()
        super(LayerGroupForm,self)._post_clean()

    class Meta:
        model = LayerGroup
        fields = "__all__"


class LayerGroupLayersForm(forms.ModelForm):
    """
    A form for LayerGroupLayers model
    """
    #publish = GroupedModelChoiceField('workspace',queryset=Publish.objects.filter(status=ResourceStatus.Enabled.name,completed__gt=0),required=False,choice_family="publish",choice_name="publish_choices")
    layer = GroupedModelChoiceField('server',queryset=WmsLayer.objects.filter(status__in = ResourceStatus.interested_layer_status_names),required=True,choice_family="interested_wmslayer",choice_name="interested_wmslayer_choices",widget=BorgSelect())
    group = GroupedModelChoiceField('workspace',queryset=LayerGroup.objects.all(),required=True,choice_family="layergroup",choice_name="layergroup_choices",widget=BorgSelect())
    #sub_group = GroupedModelChoiceField('workspace',queryset=LayerGroup.objects.all(),choice_family="layergroup",choice_name="layergroup_choices",required=False)
    def __init__(self, *args, **kwargs):
        super(LayerGroupLayersForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['group'].widget.attrs['readonly'] = True
            self.fields['layer'].widget.attrs['readonly'] = True

    class Meta:
        model = LayerGroupLayers
        fields = "__all__"
