from django.db import models
from django.utils.translation import gettext_lazy as _
from contrib.models import CommonModel
from members.rules import is_leader, is_leader_of_excursion
from contrib.rules import has_global_perm
from .excursion import Freizeit

class LJPProposal(CommonModel):
    """A proposal for LJP"""
    title = models.CharField(verbose_name=_('Title'), max_length=100,
                             blank=True, default='',
                             help_text=_('Official title of your seminar, this can differ from the informal title. Use e.g. sports climbing course instead of climbing weekend for fun.'))

    LJP_STAFF_TRAINING, LJP_EDUCATIONAL = 1, 2
    LJP_CATEGORIES = [
        (LJP_EDUCATIONAL, _('Educational programme')),
        (LJP_STAFF_TRAINING, _('Staff training'))
    ]
    category = models.IntegerField(verbose_name=_('Category'),
                                   choices=LJP_CATEGORIES,
                                   default=2,
                                   help_text=_('Type of seminar. Usually the correct choice is educational programme.'))
    LJP_QUALIFICATION, LJP_PARTICIPATION, LJP_DEVELOPMENT, LJP_ENVIRONMENT = 1, 2, 3, 4
    LJP_GOALS = [
        (LJP_QUALIFICATION, _('Qualification')),
        (LJP_PARTICIPATION, _('Participation')),
        (LJP_DEVELOPMENT, _('Personality development')),
        (LJP_ENVIRONMENT, _('Environment')),
    ]
    goal = models.IntegerField(verbose_name=_('Learning goal'),
                               choices=LJP_GOALS,
                               default=1,
                               help_text=_('Official learning goal according to LJP regulations.'))
    goal_strategy = models.TextField(verbose_name=_('Strategy'),
                                     help_text=_('How do you want to reach the learning goal? Has the goal been reached? If not, why not? If yes, what helped you to reach the goal?'),
                                     blank=True, default='')

    NOT_BW_CONTENT, NOT_BW_ROOMS, NOT_BW_CLOSE_BORDER, NOT_BW_ECONOMIC = 1, 2, 3, 4
    NOT_BW_REASONS = [
        (NOT_BW_CONTENT, _('Course content')),
        (NOT_BW_ROOMS, _('Available rooms')),
        (NOT_BW_CLOSE_BORDER, _('Close to the border')),
        (NOT_BW_ECONOMIC, _('Economic reasons')),
    ]
    not_bw_reason = models.IntegerField(verbose_name=_('Explanation if excursion not in Baden-Württemberg'),
                                        choices=NOT_BW_REASONS,
                                        default=None,
                                        blank=True,
                                        null=True,
                                        help_text=_('If the excursion takes place outside of Baden-Württemberg, please explain. Otherwise, leave this empty.'))

    excursion = models.OneToOneField(Freizeit,
                                     verbose_name=_('Excursion'),
                                     blank=True,
                                     null=True,
                                     on_delete=models.SET_NULL)

    class Meta(CommonModel.Meta):
        verbose_name = _('LJP Proposal')
        verbose_name_plural = _('LJP Proposals')
        rules_permissions = {
            'add_obj': is_leader,
            'view_obj': is_leader | has_global_perm('members.view_global_freizeit'),
            'change_obj': is_leader,
            'delete_obj': is_leader,
        }

    def __str__(self):
        return self.title

class Intervention(CommonModel):
    """An intervention during a seminar as part of a LJP proposal"""
    date_start = models.DateTimeField(verbose_name=_('Starting time'))
    duration = models.DecimalField(verbose_name=_('Duration in hours'),
                                   max_digits=4,
                                   decimal_places=2)
    activity = models.TextField(verbose_name=_('Activity and method'))

    ljp_proposal = models.ForeignKey(LJPProposal,
                                     verbose_name=_('LJP Proposal'),
                                     blank=False,
                                     on_delete=models.CASCADE)

    class Meta:
        verbose_name = _('Intervention')
        verbose_name_plural = _('Interventions')
        rules_permissions = {
            'add_obj': is_leader_of_excursion,
            'view_obj': is_leader_of_excursion | has_global_perm('members.view_global_freizeit'),
            'change_obj': is_leader_of_excursion,
            'delete_obj': is_leader_of_excursion,
        }
