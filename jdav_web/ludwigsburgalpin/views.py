from django.shortcuts import render
from django import forms
from django.http import HttpResponseRedirect

class TerminForm(forms.Form):
    title = forms.CharField(label='Termin')
    start_date = forms.DateField(widget=forms.SelectDateWidget(),
                           label='Von')
    end_date = forms.DateField(widget=forms.SelectDateWidget(),
                               label='Bis')
    group = forms.ChoiceField(label='Gruppe',
                              choices=[('Jugend', 'Jugend'),
                                       ('ASG', 'ASG'),
                                       ('Ü50-Gruppe', 'Ü50-Gruppe')])


# Create your views here.
def index(request):
    if request.method == 'POST':
        form = TerminForm(request.POST)
        if form.is_valid():
            return HttpResponseRedirect('/')
    else:
        form = TerminForm()
    return render(request, 'ludwigsburgalpin/termine.html', {'form': form.as_table()})
