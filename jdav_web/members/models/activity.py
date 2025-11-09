from django.db import models
from django.utils.translation import gettext_lazy as _

class ActivityCategory(models.Model):
    """Describes one kind of activity"""
    LJP_CATEGORIES = [('Winter', _('winter')),
                      ('Skibergsteigen', _('ski mountaineering')),
                      ('Klettern', _('climbing')),
                      ('Bergsteigen', _('mountaineering')),
                      ('Theorie', _('theory')),
                      ('Sonstiges', _('others'))]
    
    name = models.CharField(max_length=20, verbose_name=_('Name'))
    ljp_category = models.CharField(choices=LJP_CATEGORIES,
                                    verbose_name=_('LJP category'),
                                    max_length=20,
                                    help_text=_('The official category for LJP applications associated with this activity.'))
    description = models.TextField(_('Description'))

    class Meta:
        verbose_name = _('Activity')
        verbose_name_plural = _('Activities')

    def __str__(self):
        return self.name
