"""
URL configuration for shortcut_prj project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

urlpatterns = [
    path('admin/', admin.site.urls),
]

# config/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('app.urls')), # shortcut 앱의 URL 연결
]

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # 1. 관리자 페이지 (기본 제공)
    path('admin/', admin.site.urls),

    # 2. 챗봇 앱 (app) 연결
    # 사용자가 'http://127.0.0.1:8000/' 뒤에 아무것도 안 붙이고 접속했을 때
    # 'app.urls' 파일에 작성된 경로들을 따르도록 설정합니다.
    path('', include('app.urls')),
]

