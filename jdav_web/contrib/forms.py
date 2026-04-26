class RequiredFieldsMixin:
    """Mixin that appends ' *' to the label of every required field.

    Accounts for fields made required via Meta.required in addition to
    fields that are required by the model definition.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        meta_required = set(getattr(getattr(self, "Meta", None), "required", []))
        for name, field in self.fields.items():
            if field.required or name in meta_required:
                field.label = f"{field.label} *"
