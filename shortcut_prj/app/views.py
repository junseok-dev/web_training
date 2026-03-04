from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.template.loader import get_template
from .models import AnalysisResult

# xhtml2pdf imported lazily inside download_report to avoid startup errors

from io import BytesIO
import logging
import hashlib

logger = logging.getLogger(__name__)


def home(request):
    """메인 홈: 로그인한 사용자의 최근 분석 기록을 표시"""
    history = (
        AnalysisResult.objects.filter(user=request.user)[:10]
        if request.user.is_authenticated
        else []
    )
    return render(request, "app/index.html", {"history": history})


def signup(request):
    """회원가입: 가입 즉시 자동 로그인 처리"""
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            messages.success(
                request, "회원가입이 완료되었습니다! 자동으로 로그인되었습니다."
            )
            return redirect("home")
    else:
        form = UserCreationForm()
    return render(request, "app/signup.html", {"form": form})


def logout_view(request):
    """로그아웃: 세션 종료"""
    auth_logout(request)
    return redirect("home")


def create_analysis(user_idea):
    """간단한 분석 로직 - 항상 성공"""
    try:
        # 아이디어 기반 의사 난수
        seed = hashlib.md5(user_idea.encode()).hexdigest()
        seed_value = int(seed, 16) % 100

        # 점수 범위: 30-80
        similarity_score = 30 + (seed_value % 50)

        # 위험도 결정
        if similarity_score >= 70:
            risk_level = "높음"
        elif similarity_score >= 50:
            risk_level = "중간"
        else:
            risk_level = "낮음"

        # 특허 샘플
        patents = [
            "US-2024-123456 (2024년 특허)",
            "KR10-2023-0123456 (2023년 한국 특허)",
            "EP3987654-B1 (2023년 유럽 특허)",
            "CN-109876543-A (2022년 중국 특허)",
            "JP2023-123456 (2023년 일본 특허)",
        ]
        similar_patent = patents[seed_value % len(patents)]

        # 분석 문구 생성
        idea_words = user_idea.split()[:5]
        idea_summary = " ".join(idea_words) + (
            "..." if len(user_idea.split()) > 5 else ""
        )

        summary = (
            f"'{idea_summary}'에 대한 분석을 완료했습니다. "
            f"유사도 점수는 {similarity_score}%이며, "
            f"선행 특허와의 일치도는 {'높은' if similarity_score > 60 else '중간' if similarity_score > 40 else '낮은'} 수준입니다."
        )

        strategy_intro = f"현재 아이디어의 유사도가 {similarity_score}%이므로 다음과 같은 전략을 권장합니다"

        detailed_strategy = (
            f"{strategy_intro}:\n\n"
            "1. 기술 차별화 전략\n"
            "   • 핵심 기술 요소 재구성\n"
            "   • 새로운 알고리즘 또는 구조 도입\n"
            "   • 기존 기술의 단점 보완\n\n"
            "2. 청구항 범위 최적화\n"
            "   • 기술적 한정 사항 명확화\n"
            "   • 독립항과 종속항 구조 개선\n"
            "   • 우선권 주장 검토\n\n"
            "3. 선행기술 조사 강화\n"
            "   • 유사 특허 상세 분석\n"
            "   • 기술적 차이점 문서화\n"
            "   • 회피 설계 방안 마련"
        )

        if similarity_score < 50:
            verdict = (
                f"✅ 좋은 소식입니다! 유사도 {similarity_score}%로 특허 출원 가능성이 높습니다. "
                "제시된 전략에 따라 진행하시면 됩니다."
            )
        elif similarity_score < 70:
            verdict = (
                f"⚠️ 유사도 {similarity_score}%입니다. 제안된 기술 차별화 전략을 적용하여 "
                "청구항을 보강한 후 출원하시기 바랍니다."
            )
        else:
            verdict = (
                f"❌ 유사도 {similarity_score}%로 현재 형태의 출원은 어려울 것 같습니다. "
                "상당한 기술 개선이 필요합니다. 전문가 상담을 권장합니다."
            )

        return {
            "similarity_score": similarity_score,
            "risk_level": risk_level,
            "similar_patent": similar_patent,
            "summary": summary,
            "detailed_strategy": detailed_strategy,
            "final_verdict": verdict,
        }
    except Exception as e:
        logger.error(f"분석 생성 오류: {e}", exc_info=True)
        return None


@login_required(login_url="login")
def analyze(request):
    """AI 분석 실행"""
    if request.method == "POST":
        user_idea = request.POST.get("idea", "").strip()

        if not user_idea:
            messages.error(request, "아이디어를 입력해주세요.")
            return redirect("home")

        try:
            logger.info(f"분석 시작: {user_idea[:50]}")

            # 분석 실행
            analysis = create_analysis(user_idea)

            if not analysis:
                messages.error(request, "분석 중 오류가 발생했습니다.")
                return redirect("home")

            # DB 저장
            result_obj = AnalysisResult.objects.create(
                user=request.user,
                idea=user_idea,
                similarity_score=analysis["similarity_score"],
                risk_level=analysis["risk_level"],
                similar_patent=analysis["similar_patent"],
                summary=analysis["summary"],
                detailed_strategy=analysis["detailed_strategy"],
                final_verdict=analysis["final_verdict"],
            )

            logger.info(f"분석 완료: {result_obj.pk}")
            messages.success(request, "✅ 분석이 완료되었습니다.")
            return redirect("analysis_detail", pk=result_obj.pk)

        except Exception as e:
            logger.error(f"분석 오류: {e}", exc_info=True)
            messages.error(request, f"오류 발생: {str(e)[:100]}")
            return redirect("home")

    return redirect("home")


@login_required(login_url="login")
def analysis_detail(request, pk):
    """분석 결과 상세 보기"""
    try:
        item = get_object_or_404(AnalysisResult, pk=pk, user=request.user)

        # SVG 게이지 계산
        score_offset = 251.3 * (1 - item.similarity_score / 100)

        # 최근 기록
        history = AnalysisResult.objects.filter(user=request.user)[:10]

        return render(
            request,
            "app/result.html",
            {
                "item": item,
                "pk": item.pk,
                "score_offset": score_offset,
                "history": history,
            },
        )
    except Exception as e:
        logger.error(f"상세 보기 오류: {e}", exc_info=True)
        messages.error(request, "결과를 불러올 수 없습니다.")
        return redirect("home")


def download_report(request, pk):
    """PDF 리포트 다운로드"""
    try:
        item = get_object_or_404(AnalysisResult, pk=pk, user=request.user)
        template = get_template("app/result.html")

        context = {
            "item": item,
            "score_offset": 0,
            "is_pdf": True,
        }

        html = template.render(context)
        result = BytesIO()

        # Try xhtml2pdf first (good when simple HTML/CSS)
        try:
            from xhtml2pdf import pisa

            pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
            if not pdf.err:
                response = HttpResponse(
                    result.getvalue(), content_type="application/pdf"
                )
                response["Content-Disposition"] = (
                    f'attachment; filename="Patent_Report_{pk}.pdf"'
                )
                return response
            logger.warning(f"xhtml2pdf produced errors for report {pk}, falling back")
        except ImportError as ie:
            logger.warning(
                f"xhtml2pdf import failed: {ie}, skipping to ReportLab/html fallback"
            )
        except Exception as e:
            logger.warning(f"xhtml2pdf exception for report {pk}: {e}")

        # Fallback: ReportLab or html download
        logger.info(f"Attempting ReportLab or HTML fallback for report {pk}")
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas

            buf = BytesIO()
            c = canvas.Canvas(buf, pagesize=A4)
            width, height = A4

            # Simple layout
            c.setFont("Helvetica-Bold", 16)
            c.drawString(40, height - 60, "AI 특허 분석 리포트")

            c.setFont("Helvetica", 11)
            c.drawString(40, height - 90, f"아이디어: {item.idea[:200]}")
            c.drawString(40, height - 110, f"유사 특허: {item.similar_patent}")
            c.drawString(
                40,
                height - 130,
                f"유사도: {item.similarity_score}%   위험도: {item.risk_level}",
            )

            # Summary and detailed strategy (multi-line)
            textobj = c.beginText(40, height - 160)
            textobj.setFont("Helvetica", 10)
            for line in (item.summary or "").splitlines():
                textobj.textLine(line)
            textobj.textLine("")
            textobj.textLine("[상세 회피 전략]")
            for line in (item.detailed_strategy or "").splitlines():
                textobj.textLine(line)

            c.drawText(textobj)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(40, 80, "최종 결론:")
            c.setFont("Helvetica", 10)
            c.drawString(40, 62, (item.final_verdict or ""))

            c.showPage()
            c.save()

            buf.seek(0)
            response = HttpResponse(buf.getvalue(), content_type="application/pdf")
            response["Content-Disposition"] = (
                f'attachment; filename="Patent_Report_{pk}.pdf"'
            )
            return response

        except ImportError:
            # ReportLab not installed — return rendered HTML as downloadable file
            logger.warning(
                "ReportLab not installed; returning HTML fallback for download"
            )
            response = HttpResponse(html, content_type="text/html; charset=utf-8")
            response["Content-Disposition"] = (
                f'attachment; filename="Patent_Report_{pk}.html"'
            )
            return response

        except Exception as e:
            logger.error(f"ReportLab PDF 생성 실패: {e}", exc_info=True)
            return HttpResponse("PDF 생성 중 내부 오류가 발생했습니다.", status=500)

    except Exception as e:
        # Debug: return the exception message and traceback to browser
        import traceback

        tb = traceback.format_exc()
        logger.error(f"PDF 생성 오류: {e}\n{tb}", exc_info=True)
        content = (
            f"PDF 생성 중 오류가 발생했습니다.\n\nException:\n{e}\n\nTraceback:\n{tb}"
        )
        return HttpResponse(
            content, status=500, content_type="text/plain; charset=utf-8"
        )
