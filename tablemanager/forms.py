import json
from django import forms
from django.core.exceptions import ObjectDoesNotExist,ValidationError
from django.forms.widgets import HiddenInput,TextInput

from tablemanager.models import (Normalise,NormalTable,Normalise_NormalTable,Publish,
        Publish_NormalTable,ForeignTable,Input,NormalTable,Workspace,ForeignServer,DataSource,
        PublishChannel,Style)
from borg_utils.form_fields import GroupedModelChoiceField
from borg_utils.widgets import MultiWidgetLayout
from borg_utils.form_fields import GeoserverSettingForm,MetaTilingFactorField,GridSetField
from borg_utils.forms import BorgModelForm

class ForeignServerForm(BorgModelForm):
    """
    A form for ForeignServer Model
    """
    def __init__(self, *args, **kwargs):
        super(ForeignServerForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['name'].widget.attrs['readonly'] = True

    def save(self, commit=True):
        self.instance.enable_save_signal()
        return super(ForeignServerForm, self).save(commit)

    class Meta:
        model = ForeignServer
        fields = "__all__"

class ForeignTableForm(BorgModelForm):
    """
    A form for ForeignTable Model
    """
    def __init__(self, *args, **kwargs):
        super(ForeignTableForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['name'].widget.attrs['readonly'] = True

    def save(self, commit=True):
        self.instance.enable_save_signal()
        return super(ForeignTableForm, self).save(commit)

    class Meta:
        model = ForeignTable
        fields = "__all__"

class DataSourceForm(BorgModelForm):
    """
    A form for DataSource Model
    """
    def save(self, commit=True):
        self.instance.enable_save_signal()
        return super(DataSourceForm, self).save(commit)

    class Meta:
        model = DataSource
        fields = "__all__"

class InputForm(BorgModelForm):
    """
    A form for Input Model
    """
    foreign_table = GroupedModelChoiceField('server',queryset=ForeignTable.objects.all(),required=False,choice_family="foreigntable",choice_name="foreigntable_options")
    def __init__(self, *args, **kwargs):
        super(InputForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['name'].widget.attrs['readonly'] = True

    def save(self, commit=True):
        self.instance.enable_save_signal()
        return super(InputForm, self).save(commit)

    class Meta:
        model = Input
        fields = "__all__"

class NormalTableForm(BorgModelForm):
    """
    A form for NormalTable Model
    """
    def __init__(self, *args, **kwargs):
        super(NormalTableForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['name'].widget.attrs['readonly'] = True

    def save(self, commit=True):
        self.instance.enable_save_signal()
        return super(NormalTableForm, self).save(commit)

    class Meta:
        model = NormalTable
        fields = "__all__"

class PublishChannelForm(BorgModelForm):
    """
    A form for PublishChannel Model
    """
    def __init__(self, *args, **kwargs):
        super(PublishChannelForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['name'].widget.attrs['readonly'] = True

    def save(self, commit=True):
        self.instance.enable_save_signal()
        return super(PublishChannelForm, self).save(commit)

    class Meta:
        model = PublishChannel
        fields = "__all__"

class WorkspaceForm(BorgModelForm):
    """
    A form for Workspace Model
    """
    def __init__(self, *args, **kwargs):
        super(WorkspaceForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['name'].widget.attrs['readonly'] = True

    def save(self, commit=True):
        self.instance.enable_save_signal()
        return super(WorkspaceForm, self).save(commit)

    class Meta:
        model = Workspace
        fields = "__all__"

class NormaliseForm(BorgModelForm):
    """
    A form for Normalise Model
    """
    input_table = GroupedModelChoiceField('data_source',queryset=Input.objects.all(),required=True,choice_family="input",choice_name="input_options")
    dependents = forms.ModelMultipleChoiceField(queryset=NormalTable.objects.all(),required=False)
    output_table = forms.ModelChoiceField(queryset=NormalTable.objects.all(),required=False)

    def __init__(self, *args, **kwargs):
        kwargs['initial']=kwargs.get('initial',{})
        if 'instance' in kwargs and  kwargs['instance']:
            try:
                kwargs['initial']['output_table']=kwargs['instance'].normaltable
            except ObjectDoesNotExist:
                pass
            dependents = []
            for relation in (kwargs['instance'].relations):
                if relation:
                    for normal_table in relation.normal_tables:
                        if normal_table: dependents.append(normal_table)

            kwargs['initial']['dependents'] = dependents
        super(NormaliseForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['name'].widget.attrs['readonly'] = True

    def _post_clean(self):
        super(NormaliseForm,self)._post_clean()
        if self.errors:
            return

        if 'output_table' in self.cleaned_data:
            self.instance.normal_table = self.cleaned_data['output_table']
        else:
            self.instance.normal_table = None

        if 'dependents' in self.cleaned_data:
            sorted_dependents = self.cleaned_data['dependents'].order_by('pk')
        else:
            sorted_dependents = []

        self.instance.init_relations()

        pos = 0
        normal_table_pos = 0
        length = len(sorted_dependents)
        for relation in (self.instance.relations):
            normal_table_pos = 0
            for normal_table in relation.normal_tables:
                relation.set_normal_table(normal_table_pos, sorted_dependents[pos] if pos < length else None)
                pos += 1
                normal_table_pos += 1

    def save(self, commit=True):
        self.instance.enable_save_signal()
        return super(NormaliseForm, self).save(commit)

    class Meta:
        model = Normalise
        fields = ('name','input_table','dependents','output_table','sql')

class NormalTablePublishForm(BorgModelForm):
    """
    A form for normal table's Publish Model
    """
    workspace = GroupedModelChoiceField('publish_channel',queryset=Workspace.objects.all(),required=True,choice_family="workspace",choice_name="workspace_choices")
    input_table = GroupedModelChoiceField('data_source',queryset=Input.objects.all(),required=False,choice_family="input",choice_name="input_options")
    dependents = forms.ModelMultipleChoiceField(queryset=NormalTable.objects.all(),required=False)

    def __init__(self, *args, **kwargs):
        kwargs['initial']=kwargs.get('initial',{})
        if 'instance' in kwargs and  kwargs['instance']:
            #populate the dependents field value from table data
            dependents = []
            for relation in (kwargs['instance'].relations):
                if relation:
                    for normal_table in relation.normal_tables:
                        if normal_table: dependents.append(normal_table)

            kwargs['initial']['dependents'] = dependents

        super(NormalTablePublishForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['name'].widget.attrs['readonly'] = True
            self.fields['workspace'] = forms.ModelChoiceField(queryset=Workspace.objects.filter(pk=kwargs['instance'].workspace.pk))

    def _post_clean(self):
        super(NormalTablePublishForm,self)._post_clean()
        if self.errors:
            return

        #populate the value of the relation columns
        if 'dependents' in self.cleaned_data:
            sorted_dependents = self.cleaned_data['dependents'].order_by('pk')
        else:
            sorted_dependents = []

        self.instance.init_relations()

        pos = 0
        normal_table_pos = 0
        length = len(sorted_dependents)
        for relation in (self.instance.relations):
            normal_table_pos = 0
            for normal_table in relation.normal_tables:
                relation.set_normal_table(normal_table_pos, sorted_dependents[pos] if pos < length else None)
                pos += 1
                normal_table_pos += 1

    def save(self, commit=True):
        self.instance.enable_save_signal()
        return super(NormalTablePublishForm, self).save(commit)

    class Meta:
        model = Publish
        fields = ('name','workspace','interval','status','input_table','dependents','priority','sql','create_extra_index_sql')

class PublishForm(NormalTablePublishForm,GeoserverSettingForm):
    """
    A form for spatial table's Publish Model
    """
    create_cache_layer = forms.BooleanField(required=False,label="create_cache_layer",initial=True)
    create_cache_layer.setting_type = "geoserver_setting"

    server_cache_expire = forms.IntegerField(label="server_cache_expire",min_value=0,required=False,initial=0,help_text="Expire server cache after n seconds (set to 0 to use source setting)")
    server_cache_expire.setting_type = "geoserver_setting"

    client_cache_expire = forms.IntegerField(label="client_cache_expire",min_value=0,required=False,initial=0,help_text="Expire client cache after n seconds (set to 0 to use source setting)")
    client_cache_expire.setting_type = "geoserver_setting"

    def __init__(self, *args, **kwargs):
        kwargs['initial']=kwargs.get('initial',{})
        self.get_setting_from_model(*args,**kwargs)

        super(PublishForm, self).__init__(*args, **kwargs)

    def _post_clean(self):
        super(PublishForm,self)._post_clean()
        if self.errors:
            return

        self.set_setting_to_model()

    def save(self, commit=True):
        self.instance.enable_save_signal()
        return super(PublishForm, self).save(commit)

    class Meta:
        model = Publish
        fields = ('name','workspace','interval','status','input_table','dependents','priority','kmi_title','kmi_abstract','sql','create_extra_index_sql')

class StyleForm(BorgModelForm):
    """
    A form for spatial table's Style Model
    """
    default_style = forms.BooleanField(required=False,initial=False)

    def __init__(self, *args, **kwargs):
        kwargs['initial']=kwargs.get('initial',{})
        instance = None
        if 'instance' in kwargs and  kwargs['instance']:
            instance = kwargs['instance']

        if instance:
            kwargs['initial']['default_style'] = kwargs['instance'].default_style

        super(StyleForm, self).__init__(*args, **kwargs)

        builtin_style = False
        if instance and instance.pk:
            self.fields['name'].widget.attrs['readonly'] = True
            self.fields['publish'] = forms.ModelChoiceField(queryset=Publish.objects.filter(pk=kwargs['instance'].publish.pk))
            builtin_style = instance.name == "builtin"
            if builtin_style:
                self.fields['description'].widget.attrs['readonly'] = True
        
        options = json.loads(self.fields['sld'].widget.option_json)
        options['readOnly'] = builtin_style
        #import ipdb;ipdb.set_trace()
        self.fields['sld'].widget.option_json = json.dumps(options)



    def _post_clean(self):
        self.instance.set_default_style = self.cleaned_data['default_style']
        super(StyleForm,self)._post_clean()
        if self.errors:
            return


    class Meta:
        model = Style
        fields = ('name','publish','description','status','default_style','sld')
        widgets = {
                "description": forms.TextInput(attrs={"style":"width:95%"})
        }

