import os
from pathlib import Path
import django_heroku
import environ  # for Heroku.
import dj_database_url

django_heroku.settings(locals(), staticfiles=False)

env = environ.Env(
    # set casting, default value
    DEBUG=(bool, False)
)

BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("SECRET_KEY")

environment = os.environ.get("ENVIRONMENT")

if environment == "development" or environment == "test":
    DEBUG = True
else:
    DEBUG = False

INSTALLED_APPS = [
    'channels',
    'django.contrib.sites',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'storages',
    'django_inlinecss',
    'rest_framework',
    'django_rest_passwordreset',
    'corsheaders',
    'rest_framework.authtoken',
    'dj_rest_auth.registration',
    'dj_rest_auth',
    'allauth',
    'allauth.account',
    'django_filters',
    'crispy_forms',
    'drf_yasg',
    'import_export',
    # Project apps
    'accounts',
    'django_user_agents',
]

if environment == "development" or environment == "test":
    ALLOWED_HOSTS = [os.environ.get('ALLOWED_HOST_ONE'), os.environ.get('ALLOWED_HOST_TWO'),
                     os.environ.get('ALLOWED_HOST_THREE'), os.environ.get('ALLOWED_HOST_FOUR')]
else:
    ALLOWED_HOSTS = [os.environ.get('ALLOWED_HOST_ONE'), os.environ.get('ALLOWED_HOST_TWO')]


MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_user_agents.middleware.UserAgentMiddleware',
]

CORS_ALLOW_CREDENTIALS = True

if environment == "development" or environment == "test":
    CORS_ORIGIN_WHITELIST = (
        os.environ.get("FRONT_END_ONE"),
        os.environ.get("FRONT_END_TWO"),
    )
else:
    CORS_ORIGIN_WHITELIST = (
        os.environ.get("FRONT_END_ONE"),
        os.environ.get("FRONT_END_TWO"),
    )

CSRF_COOKIE_NAME = "csrftoken"

ROOT_URLCONF = 'aerofinder.urls'

# Simplified static file serving.
# https://warehouse.python.org/project/whitenoise/
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATIC_URL = '/static/'

# Extra places for collectstatic to find static files.

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

MEDIA_ROOT = os.path.join(BASE_DIR, "media")
MEDIA_URL = '/media/'
ADMIN_MEDIA_PREFIX = '/media/admin/'

AUTH_USER_MODEL = 'accounts.RAUser'
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_SUBJECT_PREFIX = ''
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
ACCOUNT_CONFIRM_EMAIL_ON_GET = True
ACCOUNT_EMAIL_CONFIRMATION_ANONYMOUS_REDIRECT_URL = '/?verification=1'
ACCOUNT_EMAIL_CONFIRMATION_AUTHENTICATED_REDIRECT_URL = '/?verification=1'
ACCOUNT_ADAPTER = 'accounts.adapter.DefaultAccountAdapterCustom'
URL_FRONT = os.environ.get("FRONT_END_ONE")
DJANGO_REST_PASSWORDRESET_NO_INFORMATION_LEAKAGE = True
DJANGO_REST_MULTITOKENAUTH_RESET_TOKEN_EXPIRY_TIME = 0.33  # 20 minutes OWASP standard
SITE_ID = 1

AUTHENTICATION_BACKENDS = (
    # default
    'django.contrib.auth.backends.ModelBackend',
    # email login
    'allauth.account.auth_backends.AuthenticationBackend',
)

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')]
        ,
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

WSGI_APPLICATION = 'aerofinder.wsgi.application'
ASGI_APPLICATION = 'aerofinder.asgi.application'

# Channels Configuration
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer'
    }
}

# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

db_from_env = dj_database_url.config(conn_max_age=600)
DATABASES['default'].update(db_from_env)

# Starting with Django 3.2, the recommended default primary key type is BigAutoField,
# which can handle larger ranges of values.
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

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

DEFAULT_RENDERER_CLASSES = (
    'rest_framework.renderers.JSONRenderer',
)
DEFAULT_AUTHENTICATION_CLASSES = (
    "rest_framework.authentication.TokenAuthentication",
)

if DEBUG:
    DEFAULT_RENDERER_CLASSES = DEFAULT_RENDERER_CLASSES + (
        'rest_framework.renderers.BrowsableAPIRenderer',
    )
    DEFAULT_AUTHENTICATION_CLASSES = DEFAULT_AUTHENTICATION_CLASSES + (
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    )

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": (
        DEFAULT_RENDERER_CLASSES
    ),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        DEFAULT_AUTHENTICATION_CLASSES
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 100,
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend']
}

# Internationalization
# https://docs.djangoproject.com/en/3.1/topics/i18n/

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://redis:6379/1",  # 'redis' is the service name in docker-compose
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Africa/Lagos'

USE_I18N = True

USE_L10N = True

USE_TZ = True
