from datetime import datetime
import unicodedata
import os
import subprocess
import time
import glob
from django.template.loader import get_template
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from wsgiref.util import FileWrapper


def media_path(fp):
    return os.path.join(os.path.join(settings.MEDIA_MEMBERLISTS, "memberlists"), fp)


def media_dir():
    return os.path.join(settings.MEDIA_MEMBERLISTS, "memberlists")


def render_tex(name, template_path, context):
    filename = name + "_" + datetime.today().strftime("%d_%m_%Y")
    filename = filename.replace(' ', '_').replace('&', '').replace('/', '_')
    # drop umlauts, accents etc.
    filename = unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore').decode()
    filename_tex = filename + '.tex'
    filename_pdf = filename + '.pdf'

    tmpl = get_template(template_path)
    res = tmpl.render(dict(context, creation_date=datetime.today().strftime('%d.%m.%Y')))
    with open(media_path(filename_tex), 'w', encoding='utf-8') as f:
        f.write(res)

    # compile using pdflatex
    oldwd = os.getcwd()
    os.chdir(media_dir())
    subprocess.call(['pdflatex', '-halt-on-error',filename_tex])
    time.sleep(1)

    # do some cleanup
    for f in glob.glob('*.log'):
        os.remove(f)
    for f in glob.glob('*.aux'):
        os.remove(f)
    #os.remove(filename_tex)
    #os.remove(filename_table)

    os.chdir(oldwd)

    # provide the user with the resulting pdf file
    with open(media_path(filename_pdf), 'rb') as pdf:
        response = HttpResponse(FileWrapper(pdf))#, content='application/pdf')
        response['Content-Type'] = 'application/pdf'
        response['Content-Disposition'] = 'attachment; filename='+filename_pdf

    return response
