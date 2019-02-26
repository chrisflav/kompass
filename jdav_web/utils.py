from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _


class RestrictedFileField(models.FileField):

    def __init__(self, *args, **kwargs):
        if "max_upload_size" in kwargs:
            self.max_upload_size = kwargs.pop("max_upload_size")
        else:
            self.max_upload_size = None
        if "content_types" in kwargs:
            self.content_types = kwargs.pop("content_types")
        else:
            self.content_types = None

        super(RestrictedFileField, self).__init__(*args, **kwargs)

    def clean(self, *args, **kwargs):
        data = super(RestrictedFileField, self).clean(*args, **kwargs)
        f = data.file
        try:
            content_type = f.content_type
            if self.content_types is not None and content_type not in self.content_types:
                raise ValidationError(_('Filetype not supported.'))
            if self.max_upload_size is not None and f._size > self.max_upload_size:
                raise ValidationError(_('Please keep filesize under {}. '
                                        'Current filesize: '
                                        '{}').format(self.max_upload_size,
                                                     f._size))
        except AttributeError as e:
            print(e)
        return data
