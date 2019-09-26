from django.shortcuts import render
from django import forms
from django.http import HttpResponseRedirect
from django.contrib.admin import widgets
from .models import Group, Termin

datepicker = forms.TextInput(attrs={'class': 'datepicker'})


class TerminForm(forms.Form):
    title = forms.CharField(label='Titel')
    start_date = forms.DateField(label='Von',
                                 widget=datepicker)
    end_date = forms.DateField(label='Bis',
                               widget=datepicker)
    group = forms.ModelChoiceField(label='Gruppe',
                                   queryset=Group.objects.all())
    responsible = forms.CharField(label='Organisator', max_length=100)
    phone = forms.CharField(max_length=20, label='Telefonnumer')
    email = forms.EmailField(max_length=100, label='Email')
    description = forms.CharField(label='Tourenbeschreibung/Anforderung',
                                  widget=forms.Textarea)


# Create your views here.
def index(request):
    if request.method == 'POST':
        form = TerminForm(request.POST)
        if form.is_valid():
            termin = Termin(title=form.cleaned_data["title"],
                            start_date=form.cleaned_data["start_date"],
                            end_date=form.cleaned_data["end_date"],
                            group=form.cleaned_data["group"],
                            responsible=form.cleaned_data["responsible"],
                            phone=form.cleaned_data["phone"],
                            email=form.cleaned_data["email"],
                            description=form.cleaned_data["description"])
            termin.save()
            return published(request)
    else:
        form = TerminForm()
    return render(request, 'ludwigsburgalpin/termine.html', {'form': form.as_table()})


def published(request):
    return render(request, 'ludwigsburgalpin/published.html')
