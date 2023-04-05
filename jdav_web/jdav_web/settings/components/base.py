deployed = '1' == os.environ.get('DJANGO_DEPLOY', '0')

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY',
			    '6_ew6l1r9_4(8=p8quv(e8b+z+k+*wm7&zxx%mcnnec99a!lpw')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOST', '').split(",")

# hostname and base url
HOST = os.environ.get('DJANGO_ALLOWED_HOST', 'localhost:8000').split(",")[0]
PROTOCOL = os.environ.get('DJANGO_PROTOCOL', 'https')
BASE_URL = os.environ.get('DJANGO_BASE_URL', HOST)

# Define media paths e.g. for image storage
MEDIA_URL = '/media/'
MEDIA_ROOT = os.environ.get('DJANGO_MEDIA_ROOT',
			    os.path.join((os.path.join(BASE_DIR, os.pardir)), "media"))
MEDIA_MEMBERLISTS = os.path.join((os.path.join(BASE_DIR, os.pardir)), "media")

# default primary key auto field type
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# prevent large files from being unreadable by the server
# see
# https://stackoverflow.com/questions/51439689/django-nginx-error-403-forbidden-when-serving-media-files-over-some-size
FILE_UPLOAD_PERMISSIONS = 0o644

# x forward

USE_X_FORWARDED_HOST = True

# Application definition

INSTALLED_APPS = [
    'contrib.apps.ContribConfig',
    'startpage.apps.StartpageConfig',
    'material.apps.MaterialConfig',
    'members.apps.MembersConfig',
    'mailer.apps.MailerConfig',
    'finance.apps.FinanceConfig',
    'ludwigsburgalpin.apps.LudwigsburgalpinConfig',
    #'easy_select2',
    'djcelery_email',
    'nested_admin',
    'django_celery_beat',
    'rules',
    'jet',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

MIDDLEWARE = [
    'django.middleware.cache.UpdateCacheMiddleware',
    'jdav_web.middleware.ForceLangMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.cache.FetchFromCacheMiddleware',
]

ROOT_URLCONF = 'jdav_web.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'jdav_web.wsgi.application'

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'rules.permissions.ObjectPermissionBackend',
)

# Password validation
# https://docs.djangoproject.com/en/1.10/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.10/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static")
]
# static root where all the static files are collected to
# use python3 manage.py collectstatic to collect static files in the STATIC_ROOT
# this is needed for deployment
STATIC_ROOT = os.environ.get('DJANGO_STATIC_ROOT',
			     '/var/www/jdav_web/static')


# Locale files (translations)

LOCALE_PATHS = (os.path.join(BASE_DIR, 'locale'),)

# Celery and Redis setup
BROKER_URL = os.environ.get('BROKER_URL', 'redis://localhost:6379/0')

# password hash algorithms used

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.BCryptPasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.ScryptPasswordHasher',
]
