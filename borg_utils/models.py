import django.db.models
from django.core.exceptions import ValidationError,NON_FIELD_ERRORS

# Create your models here.

class BorgModel(django.db.models.Model):
    @property
    def editing_mode(self):
        return hasattr(self,"changed_fields")

    @property
    def data_changed(self):
        if hasattr(self,"changed_fields"):
            return getattr(self,"changed_fields")
        else:
            return None

    def full_clean(self, exclude=None, validate_unique=True, form_cleaned=True):
        """
        Calls clean_fields, clean, and validate_unique, on the model,
        and raises a ``ValidationError`` for any errors that occurred.
        """
        errors = {}
        if exclude is None:
            exclude = []
        else:
            exclude = list(exclude)

        try:
            self.clean_fields(exclude=exclude)
        except ValidationError as e:
            errors = e.update_error_dict(errors)

        # Form.clean() is run only if other validation succeed
        if form_cleaned and not errors:
            try:
                self.clean()
            except ValidationError as e:
                errors = e.update_error_dict(errors)

        # Run unique checks, but only for fields that passed validation.
        if validate_unique:
            for name in errors.keys():
                if name != NON_FIELD_ERRORS and name not in exclude:
                    exclude.append(name)
            try:
                self.validate_unique(exclude=exclude)
            except ValidationError as e:
                errors = e.update_error_dict(errors)

        if errors:
            raise ValidationError(errors)

    class Meta:
        abstract = True
