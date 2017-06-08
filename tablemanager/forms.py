import json
from itertools import ifilter

from django import forms
from django.core.exceptions import ObjectDoesNotExist,ValidationError
from django.forms.widgets import HiddenInput,TextInput
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper

from tablemanager.models import (Normalise,NormalTable,Normalise_NormalTable,Publish,
        Publish_NormalTable,ForeignTable,Input,NormalTable,Workspace,DataSource,
        PublishChannel,DatasourceType)
from borg_utils.form_fields import GroupedModelChoiceField,CachedModelChoiceField
from borg_utils.widgets import MultiWidgetLayout
from borg_utils.form_fields import GeoserverSettingForm,MetaTilingFactorField,GridSetField,BorgSelect
from borg_utils.forms import BorgModelForm
from django.template import Context, Template

class ForeignTableForm(BorgModelForm):
    """
    A form for ForeignTable Model
    """
    def __init__(self, *args, **kwargs):
        super(ForeignTableForm, self).__init__(*args, **kwargs)
        #remove the empty label
        #self.fields['server'].empty_label=None

        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['name'].widget.attrs['readonly'] = True
            #remote the "+" icon from html page because this field is readonly
            self.fields['server'].widget = self.fields['server'].widget.widget
            self.fields['server'].widget.attrs['readonly'] = True

    class Meta:
        model = ForeignTable
        fields = "__all__"
        widgets = {
                'server': BorgSelect(),
        }

class DataSourceForm(BorgModelForm):
    """
    A form for DataSource Model
    """
    CHANGE_TYPE = 100
    def __init__(self, *args, **kwargs):
        super(DataSourceForm, self).__init__(*args, **kwargs)

        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['name'].widget.attrs['readonly'] = True
            self.fields['type'].widget.attrs['readonly'] = True

    def get_mode(self,data):
        if data and "_change_type" in data:
            return (DataSourceForm.CHANGE_TYPE,"change_type",True,False,('name','type'))

        return super(DataSourceForm,self).get_mode(data)

    def change_type(self):
        if self.instance.type == DatasourceType.DATABASE:
            self.data['sql'] = "CREATE SERVER {{self.name}} FOREIGN DATA WRAPPER oracle_fdw OPTIONS (dbserver '//<hostname>/<sid>');"
        else:
            self.data['sql'] = ""

    class Meta:
        model = DataSource
        fields = "__all__"
        widgets = {
                'type': BorgSelect(attrs={"onChange":"django.jQuery('#datasource_form').append(\"<input type='hidden' name='_change_type' value=''>\");django.jQuery('#datasource_form').submit()"}),
                'description': forms.TextInput(attrs={"style":"width:95%"})
        }

class InputForm(BorgModelForm):
    """
    A form for Input Model
    """
    INSERT_FIELDS = 100
    CHANGE_DATA_SOURCE = 101
    CHANGE_FOREIGN_TABLE = 102

    foreign_table = CachedModelChoiceField(queryset=ForeignTable.objects.all(),label_func=lambda table:table.name,required=False,choice_family="foreigntable",choice_name="foreigntable_options", 
            widget=BorgSelect(attrs={"onChange":"$('#input_form').append(\"<input type='hidden' name='_change_foreign_table' value=''>\"); $('#input_form').submit()"}))
    def __init__(self, *args, **kwargs):
        super(InputForm, self).__init__(*args, **kwargs)
        #remote the "+" icon from html page because this will trigger onchange event and cause recusive submit html form to server
        self.fields['data_source'].widget = self.fields['data_source'].widget.widget
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['name'].widget.attrs['readonly'] = True
            self.fields['data_source'].widget.attrs['readonly'] = True
            self.fields['foreign_table'].widget.attrs['readonly'] = True

    def get_mode(self,data):
        if data and "_insert_fields" in data:
            return (InputForm.INSERT_FIELDS,"insert_fields",True,False,None)
        elif data and "_change_data_source" in data:
            return (InputForm.CHANGE_DATA_SOURCE,"change_data_source",True,False,('name','data_source'))
        elif data and "_change_foreign_table" in data:
            return (InputForm.CHANGE_DATA_SOURCE,"change_foreign_table",True,False,('name','data_source','foreign_table'))

        return super(InputForm,self).get_mode(data)

    def insert_fields(self):
        self.data['source'] = self.instance.source
        self.fields['foreign_table'].queryset = ForeignTable.objects.filter(server=self.instance.data_source)
        self.fields['foreign_table'].choice_name = "foreigntable_options_{}".format(self.instance.data_source.name)
        self.fields['foreign_table'].widget.choices = self.fields['foreign_table'].choices

    def change_data_source(self):
        if not hasattr(self.instance,"data_source"):
            self.data['source'] = ""
        elif self.instance.data_source.type == DatasourceType.FILE_SYSTEM:
            self.data['source'] = self.instance.data_source.vrt
        elif self.instance.data_source.type == DatasourceType.DATABASE:
            self.fields['foreign_table'].queryset = ForeignTable.objects.filter(server=self.instance.data_source)
            self.fields['foreign_table'].choice_name = "foreigntable_options_{}".format(self.instance.data_source.name)
            self.fields['foreign_table'].widget.choices = self.fields['foreign_table'].choices
            self.data['source'] = ""
        else:
            self.data['source'] = ""

    def change_foreign_table(self):
        self.data['source'] = str(Template(self.instance.data_source.vrt).render(Context({'self':self.instance,'db':Input.DB_TEMPLATE_CONTEXT})))
        self.fields['foreign_table'].queryset = ForeignTable.objects.filter(server=self.instance.data_source)
        self.fields['foreign_table'].choice_name = "foreigntable_options_{}".format(self.instance.data_source.name)
        self.fields['foreign_table'].widget.choices = self.fields['foreign_table'].choices

    class Meta:
        model = Input
        fields = "__all__"
        widgets = {
                'data_source': BorgSelect(attrs={"onChange":"$('#input_form').append(\"<input type='hidden' name='_change_data_source' value=''>\"); $('#input_form').submit();"}),
        }

class NormalTableForm(BorgModelForm):
    """
    A form for NormalTable Model
    """
    def __init__(self, *args, **kwargs):
        super(NormalTableForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['name'].widget.attrs['readonly'] = True

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

            self.fields['publish_channel'].widget = self.fields['publish_channel'].widget.widget
            self.fields['publish_channel'].widget.attrs['readonly'] = True

    class Meta:
        model = Workspace
        fields = "__all__"
        widgets = {
                'publish_channel': BorgSelect(),
        }

class NormaliseForm(BorgModelForm):
    """
    A form for Normalise Model
    """
    input_table = GroupedModelChoiceField('data_source',queryset=Input.objects.all(),required=True,choice_family="input",choice_name="input_options")
    dependents = forms.ModelMultipleChoiceField(queryset=NormalTable.objects.all(),required=False)
    output_table = forms.ModelChoiceField(queryset=NormalTable.objects.all(),required=False,widget=BorgSelect())

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
            self.fields['output_table'].widget.attrs['readonly'] = True

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


    class Meta:
        model = Normalise
        fields = ('name','input_table','dependents','output_table','sql')

class PublishForm(BorgModelForm,GeoserverSettingForm):
    """
    A form for normal table's Publish Model
    """
    create_cache_layer = forms.BooleanField(required=False,label="create_cache_layer",initial=True)
    create_cache_layer.setting_type = "geoserver_setting"

    server_cache_expire = forms.IntegerField(label="server_cache_expire",min_value=0,required=False,initial=0,help_text="Expire server cache after n seconds (set to 0 to use source setting)")
    server_cache_expire.setting_type = "geoserver_setting"

    client_cache_expire = forms.IntegerField(label="client_cache_expire",min_value=0,required=False,initial=0,help_text="Expire client cache after n seconds (set to 0 to use source setting)")
    client_cache_expire.setting_type = "geoserver_setting"

    workspace = GroupedModelChoiceField('publish_channel',queryset=Workspace.objects.all(),required=True,choice_family="workspace",choice_name="workspace_choices",widget=BorgSelect())
    input_table = GroupedModelChoiceField('data_source',queryset=Input.objects.all(),required=False,choice_family="input",choice_name="input_options")
    dependents = forms.ModelMultipleChoiceField(queryset=NormalTable.objects.all(),required=False)

    def __init__(self, *args, **kwargs):
        kwargs['initial']=kwargs.get('initial',{})
        self.get_setting_from_model(*args,**kwargs)

        if 'instance' in kwargs and  kwargs['instance']:
            #populate the dependents field value from table data
            dependents = []
            for relation in (kwargs['instance'].relations):
                if relation:
                    for normal_table in relation.normal_tables:
                        if normal_table: dependents.append(normal_table)

            kwargs['initial']['dependents'] = dependents

        super(PublishForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['name'].widget.attrs['readonly'] = True
            self.fields['workspace'].widget.attrs['readonly'] = True


    def _post_clean(self):
        super(PublishForm,self)._post_clean()
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
    
        if self.instance and self.instance.is_spatial:
            self.set_setting_to_model()

    class Meta:
        model = Publish
        fields = ('name','workspace','interval','status','input_table','dependents','priority','sql','create_extra_index_sql')

