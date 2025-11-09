from django.db import models
from django.utils.translation import gettext_lazy as _
from utils import RestrictedFileField
from contrib.models import CommonModel
from members.rules import is_oneself
from contrib.rules import has_global_perm

class TrainingCategory(models.Model):
    """Represents a type of training, e.g. Grundausbildung, Fortbildung, Aufbaumodul, etc."""
    name = models.CharField(verbose_name=_('Name'), max_length=50)
    permission_needed = models.BooleanField(verbose_name=_('Permission needed'))

    class Meta:
        verbose_name = _('Training category')
        verbose_name_plural = _('Training categories')

    def __str__(self):
        return self.name

class MemberTraining(CommonModel):
    """Represents a training planned or attended by a member."""
    member = models.ForeignKey('Member', on_delete=models.CASCADE, related_name='traininigs', verbose_name=_('Member'))
    title = models.CharField(verbose_name=_('Title'), max_length=150)
    date = models.DateField(verbose_name=_('Date'), null=True, blank=True)
    category = models.ForeignKey(TrainingCategory, on_delete=models.PROTECT, verbose_name=_('Category'))
    activity = models.ManyToManyField('ActivityCategory', verbose_name=_('Activity'))
    comments = models.TextField(verbose_name=_('Comments'), blank=True)
    participated = models.BooleanField(verbose_name=_('Participated'), null=True)
    passed = models.BooleanField(verbose_name=_('Passed'), null=True)
    certificate = RestrictedFileField(verbose_name=_('certificate of attendance'),
                                      upload_to='training_forms',
                                      blank=True,
                                      max_upload_size=5,
                                      content_types=['application/pdf',
                                                     'image/jpeg',
                                                     'image/png',
                                                     'image/gif'])
    
    def __str__(self):
        if self.date:
            return f"{self.title} {self.date:%d.%m.%Y}"
        return f"{self.title} {_('(no date)')}"
    
    def get_activities(self):
        activity_string = ', '.join(a.name for a in self.activity.all())
        return activity_string
    get_activities.short_description = _('Activities')

    class Meta(CommonModel.Meta):
        verbose_name = _('Training')
        verbose_name_plural = _('Trainings')
        permissions = (
            ('manage_success_trainings', 'Can edit the success status of trainings.'),
        )
        rules_permissions = {
            'add_obj': is_oneself | has_global_perm('members.add_global_membertraining'),
            'view_obj': is_oneself | has_global_perm('members.view_global_membertraining'),
            'change_obj': is_oneself | has_global_perm('members.change_global_membertraining'),
            'delete_obj': is_oneself | has_global_perm('members.delete_global_membertraining'),
        }
