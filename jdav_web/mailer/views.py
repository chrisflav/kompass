from django.shortcuts import render
from django.utils.translation import ugettext_lazy as _
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import permission_required

from members.models import Group

from .models import Message


@permission_required('mailer.submit_mails', login_url='/admin/')
def index(request):
    """This is the main newsletter view"""
    return render(request, 'mailer/index.html')


@permission_required('mailer.submit_mails', login_url='/admin/')
def send(request):
    return render(request, 'mailer/send.html', {
        'groups': Group.objects.all()
    })


@permission_required('mailer.submit_mails', login_url='/admin/')
def send_mail(request):
    try:
        subject = request.POST['subject']
        content = request.POST['content']
        to_group = Group.objects.get(pk=request.POST['to_group'])
    except (KeyError, Group.DoesNotExist):
        return render(request, 'mailer/send.html', {
            'error_message': _("Please fill in every field!"),
            'groups': Group.objects.all()
        })
    else:
        msg = Message(subject=subject, content=content, to_group=to_group)
        msg.submit()
        msg.save()
        return HttpResponseRedirect(reverse('mailer:index'))
