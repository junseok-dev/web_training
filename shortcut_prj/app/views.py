from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
import asyncio
import os

# 1. 메인 홈 페이지 (이 함수가 없어서 에러가 났던 것입니다)
def home(request):
    return render(request, 'app/index.html')

# 2. 회원가입 로직
def signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'app/signup.html', {'form': form})

# 3. 로그아웃 로직
def logout_view(request):
    auth_logout(request)
    return redirect('home')

# 4. AI 분석 로직 (로그인 필요)
@login_required(login_url='login')
def analyze(request):
    if request.method == 'POST':
        user_idea = request.POST.get('idea', '')
        
        # 실제 분석 로직 호출 (src 폴더 연결 필요)
        # result = loop.run_until_complete(...)
        
        # 임시 결과값 (테스트용)
        result = {
            'similarity': {'score': 85, 'summary': '유사한 특허가 존재합니다.'},
            'infringement': {'risk_level': '높음'},
            'avoidance': {'summary': '회피 전략이 필요합니다.'}
        }

        return render(request, 'app/result.html', {
            'idea': user_idea,
            'result': result
        })
    return redirect('home')