"""
URL configuration for start_django project.

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

# start_django/urls.py (메인 설정 파일)

from django.contrib import admin
from django.urls import path, include  # include를 반드시 추가하세요!

urlpatterns = [
    path('admin/', admin.site.urls), # 관리자 페이지 (기본 설정)
    
    # ''은 주소창에 아무것도 안 쳤을 때(홈) app의 urls.py를 보겠다는 뜻입니다.
    path('', include('app.urls')), 
]
