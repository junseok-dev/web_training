from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='app/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('analyze/', views.analyze, name='analyze'),
    # pk(숫자)를 넘겨받는 경로들
    path('result/<int:pk>/', views.analysis_detail, name='analysis_detail'),
    path('download/<int:pk>/', views.download_report, name='download_report'),
]