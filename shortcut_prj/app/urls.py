from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # 메인 챗봇 화면
    path('', views.home, name='home'),
    
    # 분석 실행 로직
    path('analyze/', views.analyze, name='analyze'),
    
    # 회원가입 및 로그인/로그아웃
    path('signup/', views.signup, name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='app/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
]