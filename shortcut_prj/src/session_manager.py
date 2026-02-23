"""
Session and User Management.
"""
import uuid
from datetime import datetime, timedelta
import streamlit as st
import extra_streamlit_components as stx
from src.history_manager import HistoryManager

def get_manager():
    return stx.CookieManager()


def init_session_state():
    """Initialize session state variables."""
    if "history_manager" not in st.session_state:
        st.session_state.history_manager = HistoryManager()
        
    if "current_result" not in st.session_state:
        st.session_state.current_result = None
        
    if "streaming_text" not in st.session_state:
        st.session_state.streaming_text = ""


def get_user_id() -> str:
    """Get or create user ID from cookie."""
    cookie_manager = get_manager()
    
    # Try to get from session first
    if "user_id" in st.session_state:
        return st.session_state.user_id
        
    # Try to get from cookie
    cookie_user_id = cookie_manager.get(cookie="shortcut_user_id")
    
    if not cookie_user_id:
        # Generate new ID if not exists
        new_id = f"user_{uuid.uuid4().hex[:8]}"
        cookie_manager.set("shortcut_user_id", new_id, expires_at=datetime.now() + timedelta(days=30))
        st.session_state.user_id = new_id
        return new_id
    else:
        st.session_state.user_id = cookie_user_id
        return cookie_user_id


def load_history():
    """Load analysis history for the current user."""
    if "analysis_history" not in st.session_state:
        user_id = get_user_id()
        st.session_state.analysis_history = st.session_state.history_manager.load_recent(user_id)


def save_result_to_history(result: dict):
    """Save result to history and session."""
    st.session_state.current_result = result
    
    # Init history list if needed (though load_history guarantees it)
    if "analysis_history" not in st.session_state:
        st.session_state.analysis_history = []
        
    st.session_state.analysis_history.append(result)
    
    # Save to persistent history
    user_id = get_user_id()
    if st.session_state.history_manager.save_analysis(result, user_id):
        st.toast("✅ 분석 결과가 히스토리에 저장되었습니다!")
        
    # Keep only recent history in memory
    if len(st.session_state.analysis_history) > 20:
        st.session_state.analysis_history.pop(0)


def clear_user_history():
    """Clear history for current user."""
    user_id = get_user_id()
    st.session_state.history_manager.clear_history(user_id)
    st.session_state.analysis_history = []
    st.rerun()
