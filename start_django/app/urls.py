# app/urls.py (앱 세부 설정 파일)

from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'), # 홈 화면 연결
]