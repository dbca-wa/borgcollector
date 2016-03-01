import django.forms
from django.core.exceptions import ValidationError
from django.forms.utils import ErrorList
from django.forms.fields import Field, FileField


class BorgModelForm(django.forms.ModelForm):
    NOT_CHANGED = 0
    SAVE = 1
    EDIT = 2
    VALIDATE = 3

    def __init__(self, data=None, files=None, auto_id='id_%s', prefix=None,
                 initial=None, error_class=ErrorList, label_suffix=None,
                 empty_permitted=False, instance=None):
        super(BorgModelForm,self).__init__(data,files,auto_id,prefix,initial,error_class,label_suffix,empty_permitted,instance)
        self._mode = self.get_mode(data)

    def get_mode(self,data):
        """
        return a tuple(mode,hook,check required?,full_clean?, customized validation field list)
        """
        if data and any(key in data for key in ["_save","_continue","_saveasnew","_addanother"]):
            return (BorgModelForm.SAVE,None,True,True,None)
        elif data and "_validate" in data:
            return (BorgModelForm.VALIDATE,None,True,True,None)
        else:
            return (BorgModelForm.EDIT,"edit",False,False,None)
        

    def save(self, commit=True):
        if self._mode[0] == BorgModelForm.NOT_CHANGED:
            self.save_m2m = lambda:None
            return self.instance
        return super(BorgModelForm,self).save(commit)

    def _clean_fields(self):
        for name, field in self.fields.items()  :
            if self._mode[4] and name not in self._mode[4]: continue
            # value_from_datadict() gets the data from the data dictionaries.
            # Each widget type knows how to retrieve its own data, because some
            # widgets split data over several HTML fields.
            value = field.widget.value_from_datadict(self.data, self.files, self.add_prefix(name))
            try:
                if value and isinstance(value,basestring): value = value.strip()
                if not self._mode[2] and not value :
                    #empty value, ignore check in editing mode
                    self.cleaned_data[name] = value
                    continue

                if isinstance(field, FileField):
                    initial = self.initial.get(name, field.initial)
                    value = field.clean(value, initial)
                else:
                    value = field.clean(value)

                self.cleaned_data[name] = value

                if hasattr(self, 'clean_%s' % name):
                    value = getattr(self, 'clean_%s' % name)()
                    self.cleaned_data[name] = value
            except ValidationError as e:
                self.add_error(name, e)


    def _post_clean(self):
        opts = self._meta
        # Update the model instance with self.cleaned_data.
        if self._mode[0] == BorgModelForm.SAVE and self.instance.pk:
            #save request, check whether it is changed or not
            changed_fields = set()
            for field in self.base_fields.keys():
                if hasattr(self.instance,field) and (self.cleaned_data[field] or None) != (getattr(self.instance,field) or None):
                    changed_fields.add(field)

            self.instance.changed_fields = changed_fields
            if not changed_fields:
                self._mode=(BorgModelForm.NOT_CHANGED,None,False,False)

        self.instance = django.forms.models.construct_instance(self, self.instance, opts.fields, opts.exclude)

        if self._mode[3]:
            exclude = self._get_validation_exclusions()

            # Foreign Keys being used to represent inline relationships
            # are excluded from basic field value validation. This is for two
            # reasons: firstly, the value may not be supplied (#12507; the
            # case of providing new values to the admin); secondly the
            # object being referred to may not yet fully exist (#12749).
            # However, these fields *must* be included in uniqueness checks,
            # so this can't be part of _get_validation_exclusions().
            for name, field in self.fields.items():
                if isinstance(field, django.forms.models.InlineForeignKeyField):
                    exclude.append(name)

            try:
                self.instance.full_clean(exclude=exclude, validate_unique=False,form_cleaned=not bool(self._errors))
            except ValidationError as e:
                self._update_errors(e)

            # Validate uniqueness if needed.
            if self._validate_unique:
                self.validate_unique()
    
        if self._mode[1]:
            errors = {}
            if hasattr(self.instance,self._mode[1]):
                try:
                    getattr(self.instance,self._mode[1])()
                except ValidationError as e:
                    errors = e.update_error_dict(errors)

            if hasattr(self,self._mode[1]):
                try:
                    getattr(self,self._mode[1])()
                except ValidationError as e:
                    errors = e.update_error_dict(errors)

            if errors:
                self._update_errors(ValidationError(errors))
                

            return
