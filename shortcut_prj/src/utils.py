"""
Utility functions for the Short-Cut Patent Analysis App.
State-less helper functions.
"""
from datetime import datetime
import streamlit as st

def get_risk_color(risk_level: str) -> tuple:
    """Get color scheme based on risk level."""
    colors = {
        "high": ("#dc3545", "🔴", "metric-high"),
        "medium": ("#ffc107", "🟡", "metric-medium"),
        "low": ("#28a745", "🟢", "metric-low"),
    }
    return colors.get(risk_level.lower(), ("#6c757d", "⚪", "metric-low"))


def get_score_color(score: int) -> str:
    """Get color based on similarity score."""
    if score >= 70:
        return "#dc3545"
    elif score >= 40:
        return "#ffc107"
    else:
        return "#28a745"


def get_patent_link(patent_id: str) -> str:
    """Generate Google Patents link from patent ID."""
    # Clean patent ID (remove spaces, dashes for URL)
    clean_id = patent_id.replace(" ", "").replace("-", "")
    return f"https://patents.google.com/patent/{clean_id}"


def display_patent_with_link(patent_id: str):
    """Display patent ID with clickable link."""
    link = get_patent_link(patent_id)
    st.markdown(f"📄 `{patent_id}` [🔗 원문 보기]({link})")


def format_analysis_markdown(result: dict) -> str:
    """Format analysis result as downloadable markdown."""
    analysis = result.get("analysis", {})
    
    md = f"""# ⚡ 쇼특허 (Short-Cut) Analysis Report
> Generated: {result.get('timestamp', datetime.now().isoformat())}
> Search Type: {result.get('search_type', 'hybrid').upper()}

## 💡 User Idea
{result.get('user_idea', 'N/A')}

---

## 📊 Analysis Summary

### [1. 유사도 평가] Similarity Assessment
- **Score**: {analysis.get('similarity', {}).get('score', 0)}/100
- **Summary**: {analysis.get('similarity', {}).get('summary', 'N/A')}
- **Common Elements**: {', '.join(analysis.get('similarity', {}).get('common_elements', []))}
- **Evidence Patents**: {', '.join(analysis.get('similarity', {}).get('evidence', []))}

### [2. 침해 리스크] Infringement Risk
- **Risk Level**: {analysis.get('infringement', {}).get('risk_level', 'unknown').upper()}
- **Summary**: {analysis.get('infringement', {}).get('summary', 'N/A')}
- **Risk Factors**:
{chr(10).join(['  - ' + f for f in analysis.get('infringement', {}).get('risk_factors', [])])}
- **Evidence Patents**: {', '.join(analysis.get('infringement', {}).get('evidence', []))}

### [3. 회피 전략] Avoidance Strategy
- **Summary**: {analysis.get('avoidance', {}).get('summary', 'N/A')}
- **Strategies**:
{chr(10).join(['  - ' + s for s in analysis.get('avoidance', {}).get('strategies', [])])}
- **Alternatives**: {', '.join(analysis.get('avoidance', {}).get('alternatives', []))}

---

## 📌 Conclusion
{analysis.get('conclusion', 'N/A')}

---

## 📚 Referenced Patents
"""
    for patent in result.get("search_results", []):
        md += f"""
### {patent.get('patent_id')}
- **Title**: {patent.get('title')}
- **Score**: {patent.get('grading_score', 0):.2f} (RRF: {patent.get('rrf_score', 0):.4f})
- **Abstract**: {patent.get('abstract')}
"""
    return md
