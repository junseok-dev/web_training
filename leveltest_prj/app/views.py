import json
import time
from django.shortcuts import render, redirect
from django.conf import settings
from openai import OpenAI
from .models import Profile, QuizHistory
from .prompts import SYSTEM_PROMPT_QUIZ, SYSTEM_PROMPT_ANALYSIS

def setup(request):
    # templates/app/setup.html을 찾습니다.
    return render(request, 'app/setup.html')

def test(request):
    if request.method == "POST":
        category = request.POST.get('category')
        count = request.POST.get('count', 5)
        
        api_key = settings.OPENAI_API_KEY
        if request.user.is_authenticated:
            profile = Profile.objects.filter(user=request.user).first()
            if profile and profile.openai_api_key:
                api_key = profile.openai_api_key
            
        try:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": SYSTEM_PROMPT_QUIZ.format(category=category, num_questions=count)}],
                response_format={"type": "json_object"}
            )
            res_data = json.loads(response.choices[0].message.content)
            
            request.session['quiz_data'] = res_data.get("questions", [])
            request.session['category'] = category
            request.session['start_time'] = time.time()
            
            return render(request, 'app/test.html', {'questions': request.session['quiz_data']})
        except Exception as e:
            return render(request, 'app/setup.html', {'error': f"AI 오류: {e}"})
    return redirect('app:setup')

def result(request):
    if request.method == "POST":
        quiz_data = request.session.get('quiz_data', [])
        total_time = int(time.time() - request.session.get('start_time', time.time()))
        
        correct_count = 0
        for i, q in enumerate(quiz_data):
            user_ans = request.POST.get(f'ans_{i}')
            if user_ans is not None and int(user_ans) == q['answer_index']:
                correct_count += 1

        return render(request, 'app/result.html', {
            'score': correct_count,
            'total': len(quiz_data),
            'time': total_time,
            'analysis': "AI 레벨 판정 결과가 여기에 표시됩니다."
        })
    return redirect('app:setup')