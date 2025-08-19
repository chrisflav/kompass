from django.test import TestCase, Client
from django.urls import reverse
from django.conf import settings
from django.templatetags.static import static
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest import mock
from importlib import reload

from members.models import Member, Group, DIVERSE
from startpage import urls

from .models import Post, Section, Image


class BasicTestCase(TestCase):
    def setUp(self):
        orga = Section.objects.create(title='Organisation', urlname='orga', website_text='Section is a about everything.')
        recent = Section.objects.create(title='Recent', urlname=settings.RECENT_SECTION, website_text='Recently recent.')
        reports = Section.objects.create(title='Reports', urlname=settings.REPORTS_SECTION, website_text='Reporty reports.')
        Post.objects.create(title='Climbing is fun', urlname='climbing-is-fun', website_text='Climbing is fun!',
                            section=recent)
        Post.objects.create(title='Last trip', urlname='last-trip', website_text='A fun trip.',
                            section=reports)
        file = SimpleUploadedFile("post_image.jpg", b"file_content", content_type="image/jpeg")
        staff_post = Post.objects.create(title='Staff', urlname='staff', website_text='This is our staff: Peter.',
                                         section=orga)
        Image.objects.create(post=staff_post, f=file)
        file = SimpleUploadedFile("member_image.jpg", b"file_content", content_type="image/jpeg")
        m = Member.objects.create(prename='crazy', lastname='cool', birth_date=timezone.now().date(),
                                  email=settings.TEST_MAIL, gender=DIVERSE,
                                  image=file)
        crazy_group = Group.objects.create(name='CrazyClimbers', show_website=True)
        m.group.add(crazy_group)
        m.save()
        Group.objects.create(name='SuperClimbers', show_website=False)
        crazy_post = Post.objects.create(title='The crazy climbers', urlname='crazy', website_text='foobar',
                                         section=orga)
        crazy_post.groups.add(crazy_group)
        crazy_post.save()


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

    def test_post_with_groups(self):
        c = Client()
        url = reverse('startpage:post', args=('orga', 'crazy'))
        response = c.get(url)
        self.assertEqual(response.status_code, 200)

    def test_post_image(self):
        c = Client()
        staff_post = Post.objects.get(urlname='staff')
        img = Image.objects.get(post=staff_post)
        url = img.f.url
        response = c.get('/de' + url)
        self.assertEqual(response.status_code, 200, 'Images on posts should be visible without login.')

    def test_urlpatterns_with_redirect_url(self):
        """Test URL patterns when STARTPAGE_REDIRECT_URL is not empty"""

        # Mock settings to have a non-empty STARTPAGE_REDIRECT_URL
        with mock.patch.object(settings, 'STARTPAGE_REDIRECT_URL', 'https://example.com'):
            # Reload the urls module to trigger the conditional urlpatterns creation
            reload(urls)

            # Check that urlpatterns contains the redirect view
            url_names = [pattern.name for pattern in urls.urlpatterns if hasattr(pattern, 'name')]
            self.assertIn('index', url_names)
            self.assertEqual(len(urls.urlpatterns), 2)  # Should have index and impressum only
