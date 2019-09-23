from django.shortcuts import render
from django import forms
from django.http import HttpResponseRedirect
from django.contrib.admin import widgets
from .models import Group, Termin

from bootstrap_datepicker.widgets import DatePicker

datepicker = forms.TextInput(attrs={'class': 'datepicker'})


class TerminForm(forms.Form):
    title = forms.CharField(label='Titel')
    start_date = forms.DateField(label='Von',
                                 widget=datepicker)
    end_date = forms.DateField(label='Bis',
                               widget=datepicker)
    group = forms.ModelChoiceField(label='Gruppe',
                                   queryset=Group.objects.all())


# Create your views here.
def index(request):
    if request.method == 'POST':
        form = TerminForm(request.POST)
        if form.is_valid():
            termin = Termin(title=form.cleaned_data["title"],
                            start_date=form.cleaned_data["start_date"],
                            end_date=form.cleaned_data["end_date"],
                            group=form.cleaned_data["group"])
            termin.save()
            return published(request)
    else:
        form = TerminForm()
    return render(request, 'ludwigsburgalpin/termine.html', {'form': form.as_table()})


def published(request):
    return render(request, 'ludwigsburgalpin/published.html')
