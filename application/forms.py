from django import forms

from tablemanager.models import Publish
from application.models import Application,Application_Layers
from wmsmanager.models import WmsLayer
from borg_utils.form_fields import GroupedModelChoiceField
from borg_utils.resource_status import ResourceStatus

class ApplicationForm(forms.ModelForm):
    """
    A form for Application Model
    """
    def __init__(self, *args, **kwargs):
        super(ApplicationForm, self).__init__(*args, **kwargs) 
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            self.fields['name'].widget.attrs['readonly'] = True

    def _post_clean(self):
        if not self.errors:
            super(ApplicationForm,self)._post_clean()
        
    def save(self, commit=True):
        self.instance.enable_save_signal()
        return super(ApplicationForm, self).save(commit)

    class Meta:
        model = Application
        fields = "__all__"

class Application_LayersForm(forms.ModelForm):
    """
    A form for Application layer relationship Model
    """
    application = forms.ModelChoiceField(queryset=Application.objects.all(),required=True,empty_label=None)
    publish = GroupedModelChoiceField('workspace',queryset=Publish.objects.all(),required=False,choice_family="publish",choice_name="publish_choices")
    wmslayer = GroupedModelChoiceField('server',queryset=WmsLayer.objects.filter(status__in = ResourceStatus.interested_layer_status_names),required=False,choice_family="interested_wmslayer",choice_name="interested_wmslayer_choices")
    def __init__(self, *args, **kwargs):
        super(Application_LayersForm, self).__init__(*args, **kwargs) 
        if 'instance' in kwargs and  kwargs['instance'] and kwargs['instance'].pk:
            #self.fields['application'].widget = forms.Select(attrs={'disabled':'disabled'})
            self.fields['application'] = forms.ModelChoiceField(queryset=Application.objects.filter(pk=kwargs['instance'].application.pk),empty_label=None)

    def _post_clean(self):
        if not self.errors:
            super(Application_LayersForm,self)._post_clean()
        
    def save(self, commit=True):
        self.instance.enable_save_signal()
        return super(Application_LayersForm, self).save(commit)

    class Meta:
        model = Application_Layers
        fields = "__all__"

