from django.shortcuts import render
from django import forms
from django.http import HttpResponseRedirect
from django.contrib.admin import widgets
from django.core.validators import MinValueValidator
from .models import Termin, GRUPPE, KATEGORIE, KONDITION, TECHNIK, SAISON, EVENTART, KLASSIFIZIERUNG

datepicker = forms.TextInput(attrs={'class': 'datepicker'})


class TerminForm(forms.Form):


    title = forms.CharField(label='Titel')
    subtitle = forms.CharField(label='Untertitel')
    start_date = forms.DateField(label='Von',
                                 widget=datepicker)
    end_date = forms.DateField(label='Bis',
                               widget=datepicker)
    group = forms.ChoiceField(label='Gruppe',
                              required=True,
                              choices=GRUPPE)
    category = forms.ChoiceField(label='Kategorie', required=True, choices=KATEGORIE)
    condition = forms.ChoiceField(label='Kondition', required=True, choices=KONDITION)
    technik = forms.ChoiceField(label='Technik', required=True, choices=TECHNIK)
    saison = forms.ChoiceField(label='Saison', required=True, choices=SAISON)
    eventart = forms.ChoiceField(label='Eventart', required=True, choices=EVENTART)
    klassifizierung = forms.ChoiceField(label='Klassifizierung', required=True, choices=KLASSIFIZIERUNG)
    anforderung_hoehe = forms.IntegerField(label='Höhenmeter in Metern',
                                           required=True,
                                           validators=[
                                               MinValueValidator(0)
                                           ])
    anforderung_strecke = forms.IntegerField(label='Strecke in Kilometern',
                                             required=True,
                                             validators=[
                                                 MinValueValidator(0)
                                             ])
    anforderung_dauer = forms.IntegerField(label='Etappendauer in Stunden',
                                           required=True,
                                           validators=[
                                               MinValueValidator(0)
                                           ])
    description = forms.CharField(label='Beschreibung',
                                  widget=forms.Textarea,
                                  required=False)
    equipment = forms.CharField(label='Ausrüstung',
                                widget=forms.Textarea,
                                required=False)
    voraussetzungen = forms.CharField(label='Voraussetzungen',
                                      widget=forms.Textarea,
                                      required=False)
    max_participants = forms.IntegerField(label='Max. Teilnehmerzahl',
                                         required=True,
                                         validators=[
                                             MinValueValidator(1)
                                         ])
    responsible = forms.CharField(label='Organisator', max_length=100,
                                  required=False)
    phone = forms.CharField(max_length=20, label='Telefonnumer',
                            required=False)
    email = forms.EmailField(max_length=100, label='Email',
                             required=False)


# Create your views here.
def index(request, *args):
    if request.method == 'POST':
        form = TerminForm(request.POST)
        if form.is_valid():
            termin = Termin(title=form.cleaned_data["title"],
                            subtitle=form.cleaned_data["subtitle"],
                            start_date=form.cleaned_data["start_date"],
                            end_date=form.cleaned_data["end_date"],
                            group=form.cleaned_data["group"],
                            responsible=form.cleaned_data["responsible"],
                            phone=form.cleaned_data["phone"],
                            email=form.cleaned_data["email"],
                            category=form.cleaned_data["category"],
                            condition=form.cleaned_data["condition"],
                            technik=form.cleaned_data["technik"],
                            saison=form.cleaned_data["saison"],
                            eventart=form.cleaned_data["eventart"],
                            klassifizierung=form.cleaned_data["klassifizierung"],
                            equipment=form.cleaned_data["equipment"],
                            voraussetzungen=form.cleaned_data["voraussetzungen"],
                            max_participants=form.cleaned_data["max_participants"],
                            anforderung_hoehe=form.cleaned_data["anforderung_hoehe"],
                            anforderung_strecke=form.cleaned_data["anforderung_strecke"],
                            anforderung_dauer=form.cleaned_data["anforderung_dauer"],
                            description=form.cleaned_data["description"])
            termin.save()
            return published(request)
    else:
        form = TerminForm()
    return render(request, 'ludwigsburgalpin/termine.html', {'form': form.as_table()})


def published(request):
    return render(request, 'ludwigsburgalpin/published.html')
