"""
Feedback Logger - Simple JSONL file based feedback storage.
This data can be used for future Reranker fine-tuning.
"""
import json
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

FEEDBACK_FILE = Path(__file__).parent.parent / "logs" / "feedback.jsonl"


def save_feedback(
    query: str,
    patent_id: str,
    score: int,  # 1 for positive, -1 for negative
    user_id: str = "unknown",
    metadata: dict = None
):
    """
    Append feedback to JSONL file.
    
    Args:
        query: User's original idea/query
        patent_id: Patent publication number
        score: 1 (positive/relevant) or -1 (negative/irrelevant)
        user_id: User identifier
        metadata: Optional additional data (e.g., grading_score, risk_level)
    """
    try:
        FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        feedback_entry = {
            "query": query,
            "patent_id": patent_id,
            "score": score,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(feedback_entry, ensure_ascii=False) + "\n")
        
        logger.info(f"Feedback saved: {patent_id} -> {'+1' if score > 0 else '-1'}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save feedback: {e}")
        return False


def load_feedback(limit: int = 100) -> list:
    """Load recent feedback entries."""
    try:
        if not FEEDBACK_FILE.exists():
            return []
        
        entries = []
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))
        
        return entries[-limit:]  # Return most recent
        
    except Exception as e:
        logger.error(f"Failed to load feedback: {e}")
        return []


def get_feedback_stats() -> dict:
    """Get feedback statistics."""
    entries = load_feedback(limit=1000)
    
    positive = sum(1 for e in entries if e.get("score", 0) > 0)
    negative = sum(1 for e in entries if e.get("score", 0) < 0)
    
    return {
        "total": len(entries),
        "positive": positive,
        "negative": negative,
        "positive_rate": positive / len(entries) if entries else 0
    }
