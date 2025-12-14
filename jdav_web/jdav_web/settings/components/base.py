# ruff: noqa F821

deployed = get_var("django", "deployed", default=False)

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = get_var("django", "secret_key", default="secret")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = get_var("django", "debug", default=True)

ALLOWED_HOSTS = get_var("django", "allowed_hosts", default=["*"])

# hostname and base url
HOST = get_var("django", "host", default="localhost:8000")
PROTOCOL = get_var("django", "protocol", default="https")
BASE_URL = get_var("django", "base_url", default=HOST)

# Define media paths e.g. for image storage
MEDIA_URL = "/media/"
MEDIA_ROOT = get_var(
    "django", "media_root", default=os.path.join((os.path.join(BASE_DIR, os.pardir)), "media")
)

# default primary key auto field type
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# prevent large files from being unreadable by the server
# see
# https://stackoverflow.com/questions/51439689/django-nginx-error-403-forbidden-when-serving-media-files-over-some-size
FILE_UPLOAD_PERMISSIONS = 0o644

# x forward

USE_X_FORWARDED_HOST = True

# Application definition

INSTALLED_APPS = [
    "test_data.apps.TestDataConfig",
    "logindata.apps.LoginDataConfig",
    "contrib.apps.ContribConfig",
    "startpage.apps.StartpageConfig",
    "material.apps.MaterialConfig",
    "members.apps.MembersConfig",
    "mailer.apps.MailerConfig",
    "finance.apps.FinanceConfig",
    "ludwigsburgalpin.apps.LudwigsburgalpinConfig",
    #'easy_select2',
    "markdownify.apps.MarkdownifyConfig",
    "markdownx",
    "djcelery_email",
    "nested_admin",
    "django_celery_beat",
    "rules",
    "jet",
    "oauth2_provider",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.cache.UpdateCacheMiddleware",
    "jdav_web.middleware.ForceLangMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.cache.FetchFromCacheMiddleware",
]

X_FRAME_OPTIONS = "SAMEORIGIN"

ROOT_URLCONF = "jdav_web.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(CONFIG_DIR_PATH, "templates"), os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "jdav_web.wsgi.application"

AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",
    "rules.permissions.ObjectPermissionBackend",
)

# Password validation
# https://docs.djangoproject.com/en/1.10/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.10/howto/static-files/

STATIC_URL = "/static/"
STATICFILES_DIRS = [
    os.path.join(CONFIG_DIR_PATH, "static"),
    os.path.join(BASE_DIR, "static"),
]
# static root where all the static files are collected to
# use python3 manage.py collectstatic to collect static files in the STATIC_ROOT
# this is needed for deployment
STATIC_ROOT = get_var("django", "static_root", default="/var/www/jdav_web/static")
DEFAULT_STATIC_PATH = get_var("django", "default_static_path", default="/app/jdav_web/static")

# Locale files (translations)

LOCALE_PATHS = (os.path.join(BASE_DIR, "locale"),)

# Celery and Redis setup
BROKER_URL = get_var("django", "broker_url", default="redis://redis:6379/0")

# password hash algorithms used

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.BCryptPasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

MARKDOWNIFY = {
    "default": {
        "WHITELIST_TAGS": [
            "img",
            "abbr",
            "acronym",
            "a",
            "b",
            "blockquote",
            "em",
            "i",
            "li",
            "ol",
            "p",
            "strong",
            "ul",
            "br",
            "code",
            "span",
            "div",
            "class",
            "pre",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        ],
        "WHITELIST_ATTRS": [
            "src",
            "href",
            "style",
            "alt",
            "class",
        ],
        "LINKIFY_TEXT": {
            "PARSE_URLS": True,
            # Next key/value-pairs only have effect if "PARSE_URLS" is True
            "PARSE_EMAIL": True,
            "CALLBACKS": [],
            "SKIP_TAGS": [],
        },
    }
}

# allowed characters in names appearing in urls on the website
STARTPAGE_URL_NAME_PATTERN = r"[\w\-: *]"

# admins to contact on error messages
ADMINS = get_var("section", "admins", default=[])

LOGIN_URL = "/de/kompass/login/"
