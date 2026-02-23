"""
Core analysis logic orchestration.
"""
import time
import asyncio
import streamlit as st
from datetime import datetime
from src.patent_agent import PatentAgent, PatentSearchResult

async def run_analysis_streaming(agent, user_idea: str, results, output_container):
    """Run streaming analysis and display in real-time."""
    full_text = ""
    placeholder = output_container.empty()
    
    async for token in agent.critical_analysis_stream(user_idea, results):
        full_text += token
        placeholder.markdown(full_text + "▌")  # Cursor effect
    
    placeholder.markdown(full_text)  # Final output without cursor
    return full_text


@st.cache_resource
def load_reranker():
    """Load Reranker model (cached)."""
    try:
        from src.reranker import Reranker
        return Reranker()
    except Exception as e:
        print(f"Reranker load failed: {e}")
        return None

async def run_full_analysis(
    user_idea: str, 
    status_container, 
    streaming_container, 
    db_client, 
    use_hybrid: bool = True,
    ipc_filters: list = None
):
    """Run the complete patent analysis with streaming and caching."""
    
    # Check for cached result first
    user_id = st.session_state.get("user_id", "unknown")
    if "history_manager" in st.session_state:
        # IPC 필터가 없을 때만 캐시 사용 (단순화를 위해)
        if not ipc_filters:
            cached_result = st.session_state.history_manager.find_cached_result(user_idea, user_id)
            if cached_result:
                st.toast("⚡ 이미 분석된 아이디어입니다. 저장된 결과를 불러옵니다.")
                await asyncio.sleep(0.5)
                return cached_result

    # Create agent with cached DB client
    agent = PatentAgent(db_client=db_client)
    
    # Load Reranker
    reranker = load_reranker()
    
    results = []
    start_time = time.time()
    
    # Progress bar
    progress_bar = status_container.progress(0, text="🚀 분석 시작...")
    
    with status_container.status("🔍 특허 분석 중...", expanded=True) as status:
        # Step 1: HyDE (~3초)
        progress_bar.progress(5, text="📝 Step 1/5: 가상 청구항 생성 중... (예상: 3초)")
        status.write("📝 **Step 1/5**: HyDE - 가상 청구항 생성 중...")
        hypothetical_claim = await agent.generate_hypothetical_claim(user_idea)
        progress_bar.progress(20, text="✅ Step 1 완료!")
        status.write(f"✅ 가상 청구항 생성 완료")
        
        # Step 2: Multi-Query Search (~4초)
        search_type = "Multi-Query Hybrid" if use_hybrid else "Multi-Query Dense"
        if ipc_filters:
            search_type += f" (IPC 필터: {', '.join(ipc_filters)})"
            
        progress_bar.progress(25, text=f"🔎 Step 2/5: {search_type} 검색 중... (예상: 4초)")
        status.write(f"🔎 **Step 2/5**: {search_type} 검색 중... (3가지 관점)")
        
        # Use Multi-Query Search (Parallel) -> Get Top 15 candidates
        queries, search_results = await agent.search_multi_query(
            user_idea, top_k=15, use_hybrid=use_hybrid, ipc_filters=ipc_filters
        )
        
        # Display generated queries
        with status.expander("생성된 검색 쿼리 보기", expanded=False):
            for i, q in enumerate(queries):
                st.write(f"**Q{i+1}**: {q}")
        
        progress_bar.progress(45, text="✅ Step 2 완료!")
        status.write(f"✅ {len(search_results)}개 후보 특허 발견 (중복 제거됨)")
        
        # Step 3: Reranking (~3초)
        if reranker and search_results:
            progress_bar.progress(50, text="🎯 Step 3/5: Cross-Encoder 정밀 재정렬 중... (예상: 3초)")
            status.write("🎯 **Step 3/5**: Cross-Encoder 정밀 재정렬 중...")
            
            # Convert PatentSearchResult to dict for Reranker
            docs_for_rerank = []
            for r in search_results:
                docs_for_rerank.append({
                    "doc_obj": r, # Keep original object reference
                    "title": r.title,
                    "abstract": r.abstract,
                    "claims": r.claims
                })
            
            # Rerank
            reranked_docs = reranker.rerank(user_idea, docs_for_rerank, top_k=5)
            
            # Update results list with reranked order and scores
            results = []
            for doc in reranked_docs:
                r = doc['doc_obj']
                # Store rerank score somewhere if needed, currently not in PatentSearchResult
                results.append(r)
                
            status.write(f"✅ Top 5 특허 선정 완료 (Reranked)")
        else:
            results = search_results[:5]
            status.write("⚠️ Reranker 미사용 (Top 5 반환)")
            
        progress_bar.progress(60, text="✅ Step 3 완료!")
        
        # Step 4: Grading (~3초)
        progress_bar.progress(65, text="📊 Step 4/5: 관련성 평가 중... (예상: 3초)")
        status.write("📊 **Step 4/5**: LLM 관련성 평가 중...")
        grading = await agent.grade_results(user_idea, results)
        progress_bar.progress(80, text="✅ Step 4 완료!")
        status.write(f"✅ 평균 관련성 점수: {grading.average_score:.2f}")
        
        status.update(label="✅ 검색 완료! 분석 스트리밍 시작...", state="complete", expanded=False)
    
    # Step 5: Streaming Analysis (~10초)
    progress_bar.progress(85, text="🧠 Step 5/5: AI 분석 스트리밍 중... (예상: 10초)")
    streaming_container.markdown("### 🧠 실시간 분석 결과")
    streaming_container.caption("AI가 분석 내용을 실시간으로 생성합니다...")
    
    streamed_text = await run_analysis_streaming(agent, user_idea, results, streaming_container)
    
    # Also get structured analysis for result storage
    analysis = await agent.critical_analysis(user_idea, results)
    
    # Complete progress bar
    elapsed = time.time() - start_time
    progress_bar.progress(100, text=f"✅ 분석 완료! (소요 시간: {elapsed:.1f}초)")
    
    # Build result
    result = {
        "user_idea": user_idea,
        "search_results": [
            {
                "patent_id": r.publication_number,
                "title": r.title,
                "abstract": r.abstract,
                "claims": r.claims,
                "grading_score": r.grading_score,
                "grading_reason": r.grading_reason,
                "rrf_score": r.rrf_score,
            }
            for r in results
        ],
        "analysis": {
            "similarity": {
                "score": analysis.similarity.score,
                "common_elements": analysis.similarity.common_elements,
                "summary": analysis.similarity.summary,
                "evidence": analysis.similarity.evidence_patents,
            },
            "infringement": {
                "risk_level": analysis.infringement.risk_level,
                "risk_factors": analysis.infringement.risk_factors,
                "summary": analysis.infringement.summary,
                "evidence": analysis.infringement.evidence_patents,
            },
            "avoidance": {
                "strategies": analysis.avoidance.strategies,
                "alternatives": analysis.avoidance.alternative_technologies,
                "summary": analysis.avoidance.summary,
                "evidence": analysis.avoidance.evidence_patents,
            },
            "component_comparison": {
                "idea_components": analysis.component_comparison.idea_components,
                "matched_components": analysis.component_comparison.matched_components,
                "unmatched_components": analysis.component_comparison.unmatched_components,
                "risk_components": analysis.component_comparison.risk_components,
            },
            "conclusion": analysis.conclusion,
        },
        "streamed_analysis": streamed_text,
        "timestamp": datetime.now().isoformat(),
        "search_type": "hybrid" if use_hybrid else "dense",
    }
    
    return result
