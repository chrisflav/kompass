from django.test import TestCase, Client
from django.urls import reverse
from django.conf import settings

from members.models import Group

from .models import Post, Section


class BasicTestCase(TestCase):
    def setUp(self):
        orga = Section.objects.create(title='Organisation', urlname='orga', website_text='Section is a about everything.')
        recent = Section.objects.create(title='Recent', urlname=settings.RECENT_SECTION, website_text='Recently recent.')
        reports = Section.objects.create(title='Reports', urlname=settings.REPORTS_SECTION, website_text='Reporty reports.')
        Post.objects.create(title='Climbing is fun', urlname='climbing-is-fun', website_text='Climbing is fun!',
                            section=recent)
        Post.objects.create(title='Last trip', urlname='last-trip', website_text='A fun trip.',
                            section=reports)
        Post.objects.create(title='Staff', urlname='staff', website_text='This is our staff: Peter.',
                            section=orga)
        Group.objects.create(name='CrazyClimbers', show_website=True)
        Group.objects.create(name='SuperClimbers', show_website=False)


class ModelsTestCase(BasicTestCase):
    def test_str(self):
        orga = Section.objects.get(urlname='orga')
        self.assertEqual(str(orga), orga.title, 'String representation does not match title.')
        post = Post.objects.get(urlname='staff', section=orga)
        self.assertEqual(post.absolute_section(), orga.title, 'Displayed section of post does not match section title.')
        self.assertEqual(str(post), post.title, 'String representation does not match title.')

    def test_absolute_urlnames(self):
        orga = Section.objects.get(urlname='orga')
        recent = Section.objects.get(urlname=settings.RECENT_SECTION)
        reports = Section.objects.get(urlname=settings.REPORTS_SECTION)
        self.assertEqual(orga.absolute_urlname(), '/de/orga')

        post1 = Post.objects.get(urlname='staff', section=orga)
        self.assertEqual(post1.absolute_urlname(), '/de/orga/staff')
        self.assertEqual(post1.absolute_urlname(), reverse('startpage:post', args=(orga.urlname, 'staff')))
        post2 = Post.objects.get(urlname='climbing-is-fun', section=recent)
        self.assertEqual(post2.absolute_urlname(),
                         '/de/{name}/climbing-is-fun'.format(name=settings.RECENT_SECTION))
        self.assertEqual(post2.absolute_urlname(), reverse('startpage:post', args=(recent.urlname, 'climbing-is-fun')))
        post3 = Post.objects.get(urlname='last-trip', section=reports)
        self.assertEqual(post3.absolute_urlname(),
                         '/de/{name}/last-trip'.format(name=settings.REPORTS_SECTION))
        self.assertEqual(post3.absolute_urlname(), reverse('startpage:post', args=(reports.urlname, 'last-trip')))


class ViewTestCase(BasicTestCase):
    def test_index(self):
        c = Client()
        url = reverse('startpage:index')
        response = c.get(url)
        self.assertEqual(response.status_code, 200, 'Response code is not 200 for index.')

    def test_posts_no_category(self):
        c = Client()
        url = reverse('startpage:post', args=(settings.RECENT_SECTION, 'climbing-is-fun'))
        response = c.get(url)
        self.assertEqual(response.status_code, 200, 'Response code is not 200 for climbing post.')

    def test_posts_orga(self):
        c = Client()
        url = reverse('startpage:post', args=('orga', 'staff'))
        response = c.get(url)
        self.assertEqual(response.status_code, 200, 'Response code is not 200 for staff post.')

    def test_section(self):
        c = Client()
        url = reverse('startpage:section', args=('orga',))
        response = c.get(url)
        self.assertEqual(response.status_code, 200, 'Response code is not 200 for section page.')

    def test_section_recent(self):
        c = Client()
        url = reverse('startpage:' + settings.RECENT_SECTION)
        response = c.get(url)
        self.assertEqual(response.status_code, 200, 'Response code is not 200 for section page.')

    def test_section_reports(self):
        c = Client()
        url = reverse('startpage:' + settings.REPORTS_SECTION)
        response = c.get(url)
        self.assertEqual(response.status_code, 200, 'Response code is not 200 for section page.')

    def test_404(self):
        c = Client()
        response = c.get('/de/asdfasdfasdf')
        self.assertEqual(response.status_code, 404, 'Response code is not 404 when page not found.')

    def test_impressum(self):
        c = Client()
        response = c.get('/de/impressum')
        self.assertEqual(response.status_code, 200, 'Response code is not 200 for impressum.')

    def test_gruppen(self):
        c = Client()
        url = reverse('startpage:gruppe_detail', args=('CrazyClimbers',))
        response = c.get(url)
        self.assertEqual(response.status_code, 200, 'Response code is not 200 for group.')

    def test_gruppen_404(self):
        c = Client()
        url = reverse('startpage:gruppe_detail', args=('SuperClimbers',))
        response = c.get(url)
        self.assertEqual(response.status_code, 404, 'Response code is not 404 for group.')
        url = reverse('startpage:gruppe_detail', args=('SuperClimbersNotExisting',))
        response = c.get(url)
        self.assertEqual(response.status_code, 404, 'Response code is not 404 for group.')
