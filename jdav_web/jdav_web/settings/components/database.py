# Database
# https://docs.djangoproject.com/en/1.10/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
	'NAME': os.environ.get('DJANGO_DATABASE_NAME', 'jdav_db'),
        'USER': os.environ.get('DJANGO_DATABASE_USER', 'jdav_user'),
        'PASSWORD': os.environ.get('DJANGO_DATABASE_PASSWORD', 'jdav00jdav'),
        'HOST': os.environ.get('DJANGO_DATABASE_HOST', '127.0.0.1'),
        'PORT': os.environ.get('DJANGO_DATABASE_PORT', '5432')
    }
}

