import os

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.urls import reverse, NoReverseMatch
from utils import RestrictedFileField
from members.models import Group, Member

from markdownx.models import MarkdownxField


class Section(models.Model):
    """
    A section of the website.
    """
    title = models.CharField(verbose_name=_('Title'), max_length=50)
    urlname = models.CharField(verbose_name=_('URL'), max_length=25)
    website_text = MarkdownxField(verbose_name=_('website text'), default='', blank=True)
    show_in_navigation = models.BooleanField(verbose_name=_('Show in navigation'), default=True)

    class Meta:
        verbose_name = _('Section')
        verbose_name_plural = _('Sections')
        unique_together = ['urlname']

    def __str__(self):
        return self.title

    def absolute_urlname(self):
        try:
            return reverse('startpage:section', args=(self.urlname,))
        except NoReverseMatch:
            return _('deactivated')
    absolute_urlname.short_description = 'URL'


class Post(models.Model):
    """
    A post with title, markdown and images.
    """
    title = models.CharField(verbose_name=_('Title'), default='', max_length=50)
    urlname = models.CharField(verbose_name=_('URL'), default='', max_length=50)
    date = models.DateField(default=timezone.localdate, verbose_name=_('Date'), null=True, blank=True)
    website_text = MarkdownxField(verbose_name=_('website text'), default='', blank=True)

    groups = models.ManyToManyField(Group, verbose_name=_('Groups'), blank=True)
    detailed = models.BooleanField(verbose_name=_('detailed'), default=False)

    section = models.ForeignKey(Section, verbose_name=_('section'), on_delete=models.CASCADE, null=True, blank=False)

    def __str__(self):
        """String represenation"""
        return self.title

    class Meta:
        verbose_name = _("Post")
        verbose_name_plural = _("Posts")
        unique_together = ['section', 'urlname']

    def absolute_section(self):
        if self.section is None:
            return 'Aktuelles'
        else:
            return self.section.title
    absolute_section.short_description = _('Section')

    def absolute_urlname(self):
        try:
            if self.section is None:
                return reverse('startpage:post', args=('aktuelles', self.urlname))
            else:
                return reverse('startpage:post', args=(self.section.urlname, self.urlname))
        except NoReverseMatch:
            return _('deactivated')
    absolute_urlname.short_description = 'URL'


class Image(models.Model):
    """
    An image on a post.
    """
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    # file (not naming it file because of builtin)
    f = RestrictedFileField(_('file'),
                            upload_to='images',
                            blank=True,
                            max_upload_size=10)

    def __str__(self):
        return os.path.basename(self.f.name) if self.f.name else str(_("Empty"))

    class Meta:
        verbose_name = _('image')
        verbose_name_plural = _('images')


class MemberOnPost(models.Model):
    """
    One or multiple members on a post.
    """
    members = models.ManyToManyField(Member, verbose_name=_('Member'), blank=True)
    post = models.ForeignKey(Post, verbose_name=_('Member'), on_delete=models.CASCADE, related_name='people')
    description = models.TextField(_('Description'), default='', blank=True)
    tag = models.CharField(_('Tag'), max_length=20, default='', blank=True)

    class Meta:
        verbose_name = _("Person")
        verbose_name_plural = _("Persons")


class Link(models.Model):
    """
    Link to external resources that should be shown on the internal startpage.
    """

    title = models.CharField(_('Title'), max_length=100, default='', blank=True)
    description = models.TextField(_('Description'), default='', blank=True)
    url = models.URLField(max_length=250)

    icon = RestrictedFileField(verbose_name=_('Link Icon'),
                               upload_to='icons',
                               blank=True,
                               max_upload_size=5,
                               content_types=['image/jpeg',
                                               'image/png',
                                               'image/gif'])

    visible = models.BooleanField(verbose_name=_('Visible'), default=True)

    class Meta:
        verbose_name = _('Link')
        verbose_name_plural = _('Links')

    def __str__(self):
        return self.title
