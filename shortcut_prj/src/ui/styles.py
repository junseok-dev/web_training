"""
UI Styles and Theme Management.
"""
import streamlit as st

def get_main_css() -> str:
    """Get global CSS styles with Ivory/Light theme."""
    return """
<style>
    /* Main container */
    .stApp {
        background-color: #fdfaf5; /* Ivory Background */
        color: #1e1e1e;
    }
    
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    
    /* Text colors for light theme */
    .stMarkdown, .stText, p, span, label { color: #1e1e1e !important; }
    h1, h2, h3, h4, h5, h6 { color: #1a1a2e !important; }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: #f0f2f6 !important;
    }
    section[data-testid="stSidebar"] * {
        color: #1e1e1e !important;
    }
    
    /* Metric cards with elegant light colors */
    .metric-low {
        background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        border: 1px solid #a5d6a7;
        color: #2e7d32;
    }
    .metric-medium {
        background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%);
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        border: 1px solid #ffcc80;
        color: #ef6c00;
    }
    .metric-high {
        background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%);
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        border: 1px solid #ef9a9a;
        color: #c62828;
    }
    
    /* Risk badge */
    .risk-badge {
        font-size: 0.9rem;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-weight: 600;
    }
    .risk-high { background: #dc3545; color: white; }
    .risk-medium { background: #ffc107; color: black; }
    .risk-low { background: #28a745; color: white; }
    
    /* Analysis section - subtle ivory/grey */
    .analysis-section {
        background: rgba(0, 0, 0, 0.03);
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
        border-left: 4px solid #4a90d9;
        color: #1e1e1e;
    }
    
    /* Input areas */
    .stTextArea textarea { 
        background-color: #ffffff !important; 
        color: #1e1e1e !important;
        border: 1px solid #ddd !important;
    }
    
    .stButton > button {
        background-color: #4a90d9 !important;
        color: white !important;
        border-radius: 8px;
    }
    
    /* Streaming text animation */
    .streaming-text {
        border-left: 3px solid #4a90d9;
        padding-left: 1rem;
        animation: pulse 1s infinite;
    }
    
    @keyframes pulse {
        0%, 100% { border-left-color: #4a90d9; }
        50% { border-left-color: #1a5490; }
    }
    
    /* Header styling */
    .main-header {
        text-align: center;
        padding: 1rem 0 2rem 0;
    }
</style>
"""


def apply_theme_css():
    """Apply hardcoded Light/Ivory theme CSS."""
    # This function is now a placeholder or can be removed if not used elsewhere.
    # The main CSS is handled by get_main_css() and st.markdown() in app.py.
    pass
