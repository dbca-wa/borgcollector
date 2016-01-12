import django.forms
from django.core.exceptions import ValidationError


class BorgModelForm(django.forms.ModelForm):
    def _post_clean(self):
        opts = self._meta
        # Update the model instance with self.cleaned_data.
        self.instance = django.forms.models.construct_instance(self, self.instance, opts.fields, opts.exclude)

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

    
