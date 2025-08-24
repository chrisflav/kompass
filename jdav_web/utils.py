from datetime import datetime
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from decimal import Decimal, ROUND_HALF_DOWN
import unicodedata
from collections import OrderedDict


def file_size_validator(max_upload_size):
    """
    Returns a function checking if the supplied file has file size less or equal
    than `max_upload_size` in MB.
    """
    def check_file_size(value):
        limit = max_upload_size * 1024 * 1024
        if value.size > limit:
            raise ValidationError(_('Please keep filesize under {} MiB. '
                                    'Current filesize: '
                                    '{:10.2f} MiB.').format(max_upload_size,
                                                        value.size / 1024 / 1024))
    return check_file_size


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
        self.validators = [file_size_validator(self.max_upload_size)]

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


def cvt_to_decimal(f):
    return Decimal(f).quantize(Decimal('.01'), rounding=ROUND_HALF_DOWN)


def get_member(request):
    if not hasattr(request.user, 'member'):
        return None
    else:
        return request.user.member


def normalize_name(raw, nospaces=True, noumlaut=True):
    if noumlaut:
        raw = raw.replace('ö', 'oe').replace('ä', 'ae').replace('ü', 'ue')
    if nospaces:
        raw = raw.replace(' ', '_')
    return unicodedata.normalize('NFKD', raw).encode('ascii', 'ignore').decode('ascii')


def normalize_filename(filename, append_date=True, date=None):
    if append_date and not date:
        date = datetime.today()
    if date:
        filename = filename + "_" + date.strftime("%d_%m_%Y")
    filename = filename.replace(' ', '_').replace('&', '').replace('/', '_')
    # drop umlauts, accents etc.
    return unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore').decode()


def coming_midnight():
    base = timezone.now() + timezone.timedelta(days=1)
    return timezone.datetime(year=base.year, month=base.month, day=base.day,
                             hour=0, minute=0, second=0, microsecond=0,
                             tzinfo=base.tzinfo)

