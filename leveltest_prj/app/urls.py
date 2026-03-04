from django.urls import path
from . import views

app_name = 'app' # 템플릿의 {% url 'app:...' %}와 일치해야 함

urlpatterns = [
    path('', views.setup, name='setup'),
    path('test/', views.test, name='test'),
    path('result/', views.result, name='result'),
]