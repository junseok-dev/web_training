"""
UI Components for the application - Final Merged Version
Refined Search Results, Sidebar Reordered, Root Directory File Linking with Styled Blue Button
"""
import streamlit as st
import os
from datetime import datetime

# 유틸리티 및 스타일 임포트
from src.utils import get_risk_color, get_score_color, get_patent_link, display_patent_with_link, format_analysis_markdown
from src.ui.styles import apply_theme_css

def render_header():
    """Render the application header."""
    st.markdown("""
    <div class="main-header">
        <h1>⚡ 쇼특허 (Short-Cut)</h1>
        <p style="font-size: 1.2rem; color: #888;">특허 검색부터 분석까지, 가장 빠른 지름길</p>
    </div>
    """, unsafe_allow_html=True)

def render_sidebar(openai_api_key, db_client):
    """Render the sidebar (Order: Search -> Guide -> History -> Glossary -> Team)."""
    with st.sidebar:
        # 1. 앱 제목
        st.markdown("# ⚡ 쇼특허")
        st.markdown("### Short-Cut")
        st.divider()
        
        apply_theme_css()
        
        # ------------------------------------------------------------------
        # [스타일] 파란색 버튼 강제 적용 CSS
        # Streamlit 기본 테마와 상관없이 'primary' 버튼을 파란색으로 만듭니다.
        # ------------------------------------------------------------------
        st.markdown("""
            <style>
            div.stDownloadButton > button[kind="primary"] {
                background-color: #007bff !important; /* 파란색 */
                border-color: #007bff !important;
                color: white !important;
                border-radius: 8px; /* 약간 둥글게 */
            }
            div.stDownloadButton > button[kind="primary"]:hover {
                background-color: #0056b3 !important; /* 호버 시 진한 파란색 */
                border-color: #0056b3 !important;
            }
            </style>
        """, unsafe_allow_html=True)

        # 2. 검색 옵션 (🔧)
        st.markdown("### 🔧 검색 옵션")
        IPC_CATEGORIES = {
            "G06 (컴퓨터/AI)": "G06",
            "H04 (통신/네트워크)": "H04",
            "A61 (의료/헬스케어)": "A61",
            "H01 (반도체/전자)": "H01",
            "B60 (차량/운송)": "B60",
            "C12 (바이오/생명)": "C12",
            "F02 (기계/엔진)": "F02",
        }
        selected_categories = st.multiselect(
            "관심 기술 분야 (선택 시 필터링)",
            options=list(IPC_CATEGORIES.keys()),
            default=[],
            key="ipc_multiselect_unique",
            help="특정 기술 분야(IPC)로 검색 범위를 제한하여 정확도를 높입니다."
        )
        selected_ipc_codes = [IPC_CATEGORIES[cat] for cat in selected_categories]
        st.divider()

        # 3. 특허 가이드 (📖)
        st.markdown("### 📖 특허 가이드")
        st.caption("처음 사용하시나요? 가이드 영상을 확인하세요.")
        
        @st.dialog("📖 특허 출원 가이드", width="large")
        def show_patent_guide_popup():
            st.write("**특허 출원 전 알아야 할 핵심 정보:**")
            video_url = "https://www.youtube.com/watch?v=HSWXcMSneB4"
            st.video(video_url)
            st.write("---")
            st.caption("닫기 버튼이나 배경을 클릭하면 팝업이 닫힙니다.")
        
        if st.button("🎥 가이드 영상 보기", key="sidebar_guide_btn_unique", use_container_width=True):
            show_patent_guide_popup()
            
        st.divider()
        
        # 4. 분석 히스토리 (📜)
        st.markdown("### 📜 분석 히스토리")
        if st.session_state.get("analysis_history"):
            for i, hist in enumerate(reversed(st.session_state.analysis_history[-5:])):
                with st.expander(f"#{len(st.session_state.analysis_history)-i}: {hist['user_idea'][:20]}..."):
                    risk = hist.get('analysis', {}).get('infringement', {}).get('risk_level', 'unknown')
                    score = hist.get('analysis', {}).get('similarity', {}).get('score', 0)
                    st.write(f"🎯 유사도: {score}/100")
                    st.write(f"⚠️ 리스크: {risk.upper()}")
        else:
            st.caption("아직 분석 기록이 없습니다.")
            
        if st.button("🗑️ 기록 삭제", key="clear_history_btn_unique", use_container_width=True):
            st.session_state.analysis_history = []
            from src.session_manager import clear_user_history
            clear_user_history()
            
        st.divider()

        # 5. 자료실 (📚) - 디자인 업그레이드 (파란색 버튼)
        st.markdown("### 📚 자료실")
        
        # 파일명 지정 (프로젝트 루트 경로)
        target_filename = "지식재산권용어사전_편집본_v16.pdf"
        
        # 카드 스타일 컨테이너
        with st.container(border=True):
            # 상단: 아이콘 + 텍스트
            col_icon, col_text = st.columns([1, 4])
            with col_icon:
                st.markdown("<h2 style='text-align: center; margin: 0;'>📘</h2>", unsafe_allow_html=True)
            with col_text:
                st.markdown("**지식재산권 용어사전**")
                st.caption("v1.6 | 필수 용어 완벽 정리")
            
            # 하단: 다운로드 버튼 (파란색, 꽉 찬 너비)
            if os.path.exists(target_filename):
                with open(target_filename, "rb") as f:
                    st.download_button(
                        label="⬇️ PDF 다운로드",
                        data=f,
                        file_name="ShortCut_Glossary_v1.6.pdf",
                        mime="application/pdf",
                        use_container_width=True, # 컨테이너 너비에 맞춤 (적당한 크기)
                        type="primary" # 위에서 정의한 CSS로 인해 파란색으로 표시됨
                    )
            else:
                st.warning(f"⚠️ 파일을 찾을 수 없습니다.")
                st.caption(f"'{target_filename}' 파일을 확인해주세요.")

        st.divider()
        
        # 6. Team Info
        st.markdown("##### Team 뀨💕")
        
        return True, selected_ipc_codes

def render_search_results(result):
    """Render search result metrics and details."""
    analysis = result.get("analysis", {})
    st.divider()
    st.markdown("## 📊 분석 결과")
    
    # 1. 검색 타입 배지
    search_type = result.get("search_type", "hybrid")
    if search_type == "hybrid":
        st.success("🔀 하이브리드 검색 (Dense + BM25 + RRF)")
    else:
        st.info("🎯 Dense 검색")
    
    # 2. 메트릭 카드
    col1, col2, col3 = st.columns(3)
    with col1:
        score = analysis.get("similarity", {}).get("score", 0)
        st.metric(
            label="🎯 유사도 점수", 
            value=f"{score}/100",
            delta="위험" if score >= 70 else ("주의" if score >= 40 else "양호"),
            delta_color="normal" if score < 40 else "inverse"
        )
    with col2:
        risk_level = analysis.get("infringement", {}).get("risk_level", "unknown")
        _, emoji, _ = get_risk_color(risk_level)
        st.metric(label="⚠️ 침해 리스크", value=f"{emoji} {risk_level.upper()}")
    with col3:
        patent_count = len(result.get("search_results", []))
        st.metric(label="📚 참조 특허", value=f"{patent_count}건")
    
    # 3. 상세 분석 탭
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📝 종합 리포트", "🗺️ 특허 지형도", "🎯 유사도 분석", 
        "⚠️ 침해 리스크", "🛡️ 회피 전략", "🔬 구성요소 대비"
    ])

    # [Tab 1] 종합 리포트
    with tab1:
        st.markdown("### 📌 결론")
        st.info(analysis.get("conclusion", "분석 결과가 없습니다."))
        
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            md_content = format_analysis_markdown(result)
            st.download_button(
                label="📥 리포트 다운로드 (Markdown)",
                data=md_content,
                file_name=f"shortcut_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
                use_container_width=True
            )
        with col_d2:
            try:
                from src.pdf_generator import PDFGenerator
                import tempfile
                result_id = result.get("timestamp", "")
                pdf_key = f"pdf_data_{result_id}"
                if pdf_key not in st.session_state:
                    with st.spinner("PDF 준비 중..."):
                        pdf_gen = PDFGenerator()
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                            pdf_path = pdf_gen.generate_report(result, tmp.name)
                            with open(pdf_path, "rb") as f:
                                st.session_state[pdf_key] = f.read()
                st.download_button(
                    label="📄 리포트 다운로드 (PDF)",
                    data=st.session_state[pdf_key],
                    file_name=f"shortcut_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"PDF 생성 실패: {e}")
        
        st.divider()
        st.markdown("### 📣 분석 품질 피드백")
        st.caption("이 분석 결과가 도움이 되었나요? 피드백을 남겨주시면 검색 품질 개선에 활용됩니다.")
        
        from src.feedback_logger import save_feedback
        user_idea = result.get("user_idea", "")
        search_results = result.get("search_results", [])
        user_id = st.session_state.get("user_id", "unknown")
        
        if search_results:
            with st.expander("🔍 특허별 관련성 평가하기", expanded=False):
                for i, patent in enumerate(search_results[:5]):
                    patent_id = patent.get("patent_id", f"unknown_{i}")
                    title = patent.get("title", "제목 없음")[:50]
                    grading_score = patent.get("grading_score", 0)
                    fc1, fc2, fc3 = st.columns([4, 1, 1])
                    with fc1:
                        st.markdown(f"**{i+1}. {title}...** ({grading_score:.0%})")
                    with fc2:
                        if st.button("👍", key=f"fb_pos_{patent_id}_{i}"):
                            save_feedback(user_idea, patent_id, 1, user_id, {"title": title})
                            st.toast(f"✅ 피드백 저장됨!")
                    with fc3:
                        if st.button("👎", key=f"fb_neg_{patent_id}_{i}"):
                            save_feedback(user_idea, patent_id, -1, user_id, {"title": title})
                            st.toast(f"❌ 피드백 저장됨!")

    # [Tab 2] 특허 지형도
    with tab2:
        try:
            from src.ui.visualization import render_patent_map
            render_patent_map(result)
        except ImportError:
            st.warning("시각화 모듈을 찾을 수 없습니다.")
        except Exception as e:
            st.error(f"지형도 렌더링 오류: {e}")

    # [Tab 3] 유사도 분석
    with tab3:
        similarity = analysis.get("similarity", {})
        st.markdown(f"### 유사도 점수: {similarity.get('score', 0)}/100")
        st.write(similarity.get("summary", "N/A"))
        st.markdown("**공통 기술 요소:**")
        for elem in similarity.get("common_elements", []):
            st.markdown(f"- {elem}")
        st.markdown("**근거 특허:**")
        for patent in similarity.get("evidence", []):
            display_patent_with_link(patent)
    
    # [Tab 4] 침해 리스크
    with tab4:
        infringement = analysis.get("infringement", {})
        st.write(infringement.get("summary", "N/A"))
        st.markdown("**위험 요소:**")
        for factor in infringement.get("risk_factors", []):
            st.markdown(f"- ⚠️ {factor}")
        st.markdown("**근거 특허:**")
        for patent in infringement.get("evidence", []):
            display_patent_with_link(patent)
            
    # [Tab 5] 회피 전략
    with tab5:
        avoidance = analysis.get("avoidance", {})
        st.markdown(f"**권장 전략**: {avoidance.get('summary', 'N/A')}")
        st.markdown("**회피 설계 방안:**")
        for strategy in avoidance.get("strategies", []):
            st.markdown(f"- ✅ {strategy}")
        st.markdown("**대안 기술:**")
        for alt in avoidance.get("alternatives", []):
            st.markdown(f"- 💡 {alt}")
            
    # [Tab 6] 구성요소 대비
    with tab6:
        comp = analysis.get("component_comparison", {})
        st.markdown("### 🔬 구성요소 대비표")
        st.caption("사용자 아이디어의 구성요소와 선행 특허 비교 분석")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### 📋 아이디어 구성요소")
            for c in comp.get("idea_components", []):
                st.markdown(f"- {c}")
        with col2:
            st.markdown("#### ✅ 일치 (선행 특허에 존재)")
            for c in comp.get("matched_components", []):
                st.markdown(f"- 🔴 {c}")

    # 실시간 분석 로그
    if result.get("streamed_analysis"):
        st.divider()
        st.markdown("### 🧠 실시간 분석 내용")
        with st.expander("상세 분석 로그 보기"):
            st.markdown(result["streamed_analysis"])

def render_footer():
    """Render the application footer."""
    st.divider()
    st.markdown("""
    <div style="text-align: center; color: #999; font-size: 0.8rem; margin-top: 2rem; padding-bottom: 2rem;">
        <p>⚠️ <b>면책 조항 (Disclaimer)</b></p>
        <p>본 시스템이 제공하는 모든 분석 결과는 RAG(Retrieval-Augmented Generation) 기술 및 고도화된 AI 알고리즘에 의해 도출된 선행 기술 조사 참고 데이터입니다. 본 정보는 데이터 기반의 통계적 예측치일 뿐, 어떠한 경우에도 국가 기관의 공식적인 판정이나 법적 효력을 가진 증빙 자료로 활용될 수 없음을 명시합니다.

실제 특허권의 유효성, 침해 여부 및 등록 가능성에 대한 최종적인 판단은 고도의 전문성을 요하는 영역이므로, 반드시 공인된 전문 변리사의 정밀한 법률 검토 및 자문을 거치시기를 강력히 권고드립니다.

쇼특허(Short-Cut) 팀은 제공되는 정보의 정밀도 향상을 위해 최선을 다하고 있으나, 데이터의 완전성이나 최신성, 혹은 이용자의 특정 목적 부합 여부에 대해 어떠한 명시적·묵시적 보증도 하지 않습니다. 따라서 본 서비스의 분석 내용을 신뢰하여 행해진 이용자의 개별적 판단이나 투자, 법적 대응 등 제반 활동으로 인해 발생하는 직·간접적인 손실에 대하여 당사는 일체의 법적 책임(Liability)을 부담하지 않음을 알려드립니다.</p>
        <p>© 2026 Short-Cut Team. All rights reserved.</p>
    </div>
    """, unsafe_allow_html=True)