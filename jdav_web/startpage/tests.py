from django.test import TestCase, Client
from django.urls import reverse

from members.models import Group

from .models import Post, Section


class ModelsTestCase(TestCase):
    def setUp(self):
        orga = Section.objects.create(title='Organisation', urlname='orga', website_text='Section is a about everything.')
        Post.objects.create(title='Climbing is fun', urlname='climbing-is-fun', website_text='Climbing is fun!')
        Post.objects.create(title='Staff', urlname='staff', website_text='This is our staff: Peter.',
                            section=orga)

    def test_str(self):
        orga = Section.objects.get(urlname='orga')
        self.assertEqual(str(orga), orga.title, 'String representation does not match title.')
        post = Post.objects.get(urlname='staff', section=orga)
        self.assertEqual(post.absolute_section(), orga.title, 'Displayed section of post does not match section title.')
        self.assertEqual(str(post), post.title, 'String representation does not match title.')
        for post in Post.objects.filter(section=None):
            self.assertEqual(post.absolute_section(), 'Aktuelles', 'Displayed section of post does not "Aktuelles".')

    def test_absolute_urlnames(self):
        orga = Section.objects.get(urlname='orga')
        self.assertEqual(orga.absolute_urlname(), '/de/orga')

        post1 = Post.objects.get(urlname='staff', section=orga)
        self.assertEqual(post1.absolute_urlname(), '/de/orga/staff')
        post2 = Post.objects.get(urlname='climbing-is-fun', section=None)
        self.assertEqual(post2.absolute_urlname(), '/de/aktuelles/climbing-is-fun')


class ViewTestCase(TestCase):
    def setUp(self):
        orga = Section.objects.create(title='Organisation', urlname='orga', website_text='Section is a about everything.')
        Post.objects.create(title='Climbing is fun', urlname='climbing-is-fun', website_text='Climbing is fun!')
        Post.objects.create(title='Staff', urlname='staff', website_text='This is our staff: Peter.',
                            section=orga)
        Group.objects.create(name='CrazyClimbers', show_website=True)
        Group.objects.create(name='SuperClimbers', show_website=False)

    def test_index(self):
        c = Client()
        url = reverse('startpage:index')
        response = c.get(url)
        self.assertEqual(response.status_code, 200, 'Response code is not 200 for index.')

    def test_posts_no_category(self):
        c = Client()
        url = reverse('startpage:post', args=('aktuelles', 'climbing-is-fun'))
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
        url = reverse('startpage:aktuelles')
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
