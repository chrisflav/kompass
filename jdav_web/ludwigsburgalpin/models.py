from django.db import models
from django.core.validators import MinValueValidator

GRUPPE = [
    ('ASG', 'Alpinsportgruppe'),
    ('OGB', 'Ortsgruppe Bietigheim'),
    ('OGV', 'Ortsgruppe Vaihingen'),
    ('JUG', 'Jugend'),
    ('FAM', 'Familie'),
    ('Ü30', 'Ü30'),
    ('MTB', 'Mountainbike'),
    ('RA',  'RegioAktiv'),
    ('SEK', 'Sektion'),
]
KATEGORIE = [
    ('WAN', 'Wandern'),
    ('BW', 'Bergwandern'),
    ('KST', 'Klettersteig'),
    ('KL', 'Klettern'),
    ('SKI', 'Piste, Loipe'),
    ('SCH', 'Schneeschuhgehen'),
    ('ST', 'Skitour'),
    ('STH', 'Skihochtour'),
    ('HT', 'Hochtour'),
    ('MTB', 'Montainbike'),
    ('AUS', 'Ausbildung'),
    ('SON', 'Sonstiges z.B. Treffen')
]
KONDITION = [
    ('gering', 'gering'),
    ('mittel', 'mittel'),
    ('groß', 'groß'),
    ('sehr groß', 'sehr groß'),
]
TECHNIK = [
    ('leicht', 'leicht'),
    ('mittel', 'mittel'),
    ('schwer', 'schwer'),
    ('sehr schwer', 'sehr schwer'),
]
SAISON = [
    ('ganzjährig','ganzjährig'),
    ('Indoor', 'Indoor'),
    ('Sommer', 'Sommer'),
    ('Winter', 'Winter'),
]
EVENTART = [
    ('Einzeltermin', 'Einzeltermin',),
    ('Mehrtagesevent', 'Mehrtagesevent',),
    ('Regelmäßiges Event/Training', 'Regelmäßiges Event/Training',),
    ('Tagesevent', 'Tagesevent',),
    ('Wochenendevent', 'Wochenendevent',),
]
KLASSIFIZIERUNG = [
    ('Gemeinschaftstour', 'Gemeinschaftstour'),
    ('Ausbildung', 'Ausbildung'),
]


# Create your models here.
class Termin(models.Model):
    title = models.CharField('Titel', max_length=100)
    subtitle = models.CharField('Untertitel', max_length=100, blank=True)
    start_date = models.DateField('Von')
    end_date = models.DateField('Bis')
    group = models.CharField('Gruppe',
                              choices=GRUPPE,
                              max_length=100)
    responsible = models.CharField('Organisator', max_length=100, blank=False)
    phone = models.CharField(max_length=20, verbose_name='Telefonnumer', blank=True)
    email = models.EmailField(max_length=100, verbose_name='Email', blank=False)
    category = models.CharField('Kategorie', blank=False, choices=KATEGORIE, max_length=100,
                                default='SON')
    condition = models.CharField('Kondition', blank=False, choices=KONDITION, max_length=100,
                                 default='mittel')
    technik = models.CharField('Technik', blank=False, choices=TECHNIK, max_length=100,
                               default='mittel')
    saison = models.CharField('Saison', blank=False, choices=SAISON, max_length=100,
                              default='ganzjährig')
    eventart = models.CharField('Eventart', blank=False, choices=EVENTART, max_length=100,
                                default='Einzeltermin')
    klassifizierung = models.CharField('Klassifizierung', blank=False, choices=KLASSIFIZIERUNG,
                                       max_length=100,
                                       default='Gemeinschaftstour')
    equipment = models.TextField('Ausrüstung',
                                 blank=True)
    voraussetzungen = models.TextField('Voraussetzungen',
                                       blank=True)
    description = models.TextField('Beschreibung',
                                   blank=True)
    max_participants = models.IntegerField('Max. Teilnehmerzahl',
                                           blank=False,
                                           validators=[
                                               MinValueValidator(1)
                                           ],
                                           default=10)
    anforderung_hoehe = models.IntegerField('Höhenmeter in Meter',
                                            blank=True,
                                            validators=[
                                                MinValueValidator(0)
                                            ],
                                            default=0)
    anforderung_strecke = models.IntegerField('Strecke in Kilometer',
                                              blank=True,
                                              validators=[
                                                  MinValueValidator(0)
                                              ],
                                              default=0)
    anforderung_dauer = models.IntegerField('Etappendauer in Stunden',
                                            blank=True,
                                            validators=[
                                                MinValueValidator(0)
                                            ],
                                            default=0)

    def __str__(self):
        return "{} {}".format(self.title, str(self.group))

    class Meta:
        verbose_name = 'Termin'
        verbose_name_plural = 'Termine'
