class RequiredFieldsMixin:
    """Mixin that renders labels as 'Label:*' for required fields, 'Label:' otherwise.

    Accounts for fields made required via Meta.required in addition to
    fields that are required by the model definition.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
        meta_required = set(getattr(getattr(self, "Meta", None), "required", []))
        for name, field in self.fields.items():
            if field.required or name in meta_required:
                field.label = f"{field.label}:*"
            else:
                field.label = f"{field.label}:"
