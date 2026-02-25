from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.template.loader import get_template
from .models import AnalysisResult
from asgiref.sync import sync_to_async
from xhtml2pdf import pisa  # pip install xhtml2pdf 가 필요합니다.
from io import BytesIO

# 1. 메인 홈: 로그인한 사용자의 최근 분석 기록 10개를 사이드바용으로 가져옵니다.
def home(request):
    history = AnalysisResult.objects.filter(user=request.user)[:10] if request.user.is_authenticated else []
    return render(request, 'app/index.html', {'history': history})

# 2. 회원가입: 가입 즉시 자동 로그인 처리 및 성공 메시지를 전달합니다.
def signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            messages.success(request, "회원가입이 완료되었습니다! 자동으로 로그인되었습니다.")
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'app/signup.html', {'form': form})

# 3. 로그아웃: 세션을 종료하고 메인 화면으로 이동합니다.
def logout_view(request):
    auth_logout(request)
    return redirect('home')

# 4. AI 분석 실행: LLM 분석 데이터(유사 특허, 상세 제언, 결론)를 생성하여 저장합니다.
@login_required(login_url='login')
async def analyze(request):
    if request.method == 'POST':
        user_idea = request.POST.get('idea', '')
        
        # [데이터 시뮬레이션] 실제 운영 시에는 여기서 LLM API를 호출하여 결과를 받습니다.
        score = 82
        risk = "높음" if score > 70 else "보통"
        
        # 비동기 환경에서 안전하게 DB 객체를 생성합니다.
        result_obj = await sync_to_async(AnalysisResult.objects.create)(
            user=request.user,
            idea=user_idea,
            similarity_score=score,
            risk_level=risk,
            similar_patent="KR10-2023-0123456 (인공지능 기반 데이터 처리 장치)",
            summary="입력하신 아이디어의 핵심 구성이 선행 특허의 청구항 제1항과 기술적으로 80% 이상 유사한 것으로 분석됩니다.",
            detailed_strategy="1. 데이터 전처리 단계에서 독자적인 암호화 필터링 계층을 추가하여 기술적 차별성을 확보하세요.\n2. 결과 출력 인터페이스에 사용자 감성 분석 데이터를 결합하는 고유 UI를 설계에 반영하세요.",
            final_verdict="현재 상태로는 특허 등록 가능성이 낮습니다. 제언된 상세 회피 전략을 바탕으로 기술적 보강을 거친 후 재출원하시기 바랍니다."
        )
        
        # 생성된 데이터의 pk를 가지고 상세 페이지로 리다이렉트합니다.
        return redirect('analysis_detail', pk=result_obj.pk)
    return redirect('home')

# 5. 상세 보기: DB에서 데이터를 불러와 100% 배율에 최적화된 결과 화면을 렌더링합니다.
@login_required(login_url='login')
async def analysis_detail(request, pk):
    # 특정 분석 기록을 가져오고, 없으면 404 에러를 발생시킵니다.
    item = await sync_to_async(get_object_or_404)(AnalysisResult, pk=pk, user=request.user)
    
    # SVG 게이지 오프셋 계산 (반지름 40 기준 원둘레 약 251.3)
    score_offset = 251.3 * (1 - item.similarity_score / 100)
    
    # 사이드바용 최근 기록 목록
    history = await sync_to_async(list)(AnalysisResult.objects.filter(user=request.user)[:10])

    return render(request, 'app/result.html', {
        'item': item,
        'pk': item.pk,  # 템플릿의 URL 태그에서 사용됩니다.
        'score_offset': score_offset,
        'history': history
    })

# 6. 리포트 저장: 현재 분석 결과를 PDF 파일로 변환하여 다운로드합니다.
def download_report(request, pk):
    item = get_object_or_404(AnalysisResult, pk=pk, user=request.user)
    template = get_template('app/result.html')
    
    # PDF는 동적 자바스크립트를 지원하지 않으므로 정적인 데이터를 전달합니다.
    context = {
        'item': item,
        'score_offset': 0,
        'is_pdf': True  # PDF 출력 시 불필요한 버튼 등을 숨기기 위한 플래그
    }
    
    html = template.render(context)
    result = BytesIO()
    
    # 한글 깨짐 방지를 위해 UTF-8 인코딩을 적용하여 PDF를 생성합니다.
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
    
    if not pdf.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        # 파일명을 영문/숫자 조합으로 설정하여 다운로드를 강제합니다.
        response['Content-Disposition'] = f'attachment; filename="Patent_Analysis_Report_{pk}.pdf"'
        return response
    
    return HttpResponse("PDF 생성 중 오류가 발생했습니다.", status=400)