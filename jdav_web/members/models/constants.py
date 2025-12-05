from django.utils.translation import gettext_lazy as _

GEMEINSCHAFTS_TOUR = MUSKELKRAFT_ANREISE = MALE = 0
FUEHRUNGS_TOUR = OEFFENTLICHE_ANREISE = FEMALE = 1
AUSBILDUNGS_TOUR = FAHRGEMEINSCHAFT_ANREISE = DIVERSE = 2

WEEKDAYS = (
    (0, _("Monday")),
    (1, _("Tuesday")),
    (2, _("Wednesday")),
    (3, _("Thursday")),
    (4, _("Friday")),
    (5, _("Saturday")),
    (6, _("Sunday")),
)
