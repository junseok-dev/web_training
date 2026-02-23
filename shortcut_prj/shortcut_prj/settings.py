import os
from pathlib import Path

# 1. 경로 설정
BASE_DIR = Path(__file__).resolve().parent.parent

# 2. 보안 설정 (개발용)
SECRET_KEY = 'django-insecure-your-unique-secret-key'
DEBUG = True
ALLOWED_HOSTS = []

# 3. 앱 등록 (중요: 'app'이 반드시 포함되어야 함)
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # 우리가 만든 챗봇 앱
    'app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# 프로젝트 설정 폴더 이름에 맞게 수정됨
ROOT_URLCONF = 'shortcut_prj.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

# 프로젝트 이름에 맞게 수정됨
WSGI_APPLICATION = 'shortcut_prj.wsgi.application'

# 4. 데이터베이스 (SQLite 사용)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# 5. 비밀번호 검증
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

# 6. 언어 및 지역 설정 (한국어 설정)
LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = True

# 7. 정적 파일 (CSS, JS) 설정
STATIC_URL = 'static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

# 8. 로그인/로그아웃 리다이렉트 설정
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# 9. 에러가 났던 기본 PK 필드 설정 (더 호환성 높은 경로로 수정)
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'