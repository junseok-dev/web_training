"""
History Manager - SQLite based persistent storage for analysis history.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

DB_PATH = Path(__file__).parent / "data" / "history.db"

class HistoryManager:
    def __init__(self):
        self._init_db()
        
    def _init_db(self):
        """Initialize SQLite database table and migrate schema."""
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Create table if not exists with user_id
        c.execute('''
            CREATE TABLE IF NOT EXISTS analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                user_id TEXT,
                user_idea TEXT,
                result_json TEXT,
                risk_level TEXT,
                score INTEGER
            )
        ''')
        
        # Check if user_id column exists (Migration for existing DB)
        c.execute("PRAGMA table_info(analysis_history)")
        columns = [info[1] for info in c.fetchall()]
        if 'user_id' not in columns:
            print("Migrating DB: Adding user_id column...")
            try:
                c.execute("ALTER TABLE analysis_history ADD COLUMN user_id TEXT")
                # Assign default user_id for existing records
                c.execute("UPDATE analysis_history SET user_id = 'legacy_user'")
            except Exception as e:
                print(f"Migration failed: {e}")
            
        conn.commit()
        conn.close()
        
    def save_analysis(self, result: Dict, user_id: str):
        """Save analysis result to DB with user_id."""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            analysis = result.get('analysis', {})
            risk = analysis.get('infringement', {}).get('risk_level', 'unknown')
            score = analysis.get('similarity', {}).get('score', 0)
            
            c.execute('''
                INSERT INTO analysis_history (timestamp, user_id, user_idea, result_json, risk_level, score)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                result.get('timestamp', datetime.now().isoformat()),
                user_id,
                result.get('user_idea', ''),
                json.dumps(result, ensure_ascii=False),
                risk,
                score
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Failed to save history: {e}")
            return False
            
    def load_recent(self, user_id: str, limit: int = 20) -> List[Dict]:
        """Load recent analysis history for specific user."""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            c.execute('''
                SELECT result_json FROM analysis_history 
                WHERE user_id = ?
                ORDER BY id DESC LIMIT ?
            ''', (user_id, limit))
            
            rows = c.fetchall()
            history = [json.loads(row['result_json']) for row in rows]
            
            conn.close()
            return history
        except Exception as e:
            print(f"Failed to load history: {e}")
            return []

    def find_cached_result(self, user_idea: str, user_id: str) -> Optional[Dict]:
        """Find the most recent identical query in history to act as a cache."""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            # Use exact match for now. In future, semantic similarity could be used.
            c.execute('''
                SELECT result_json FROM analysis_history 
                WHERE user_id = ? AND user_idea = ?
                ORDER BY id DESC LIMIT 1
            ''', (user_id, user_idea))
            
            row = c.fetchone()
            conn.close()
            
            if row:
                return json.loads(row['result_json'])
            return None
        except Exception as e:
            print(f"Failed to check cache: {e}")
            return None

    def clear_history(self, user_id: str):
        """Delete history for specific user."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM analysis_history WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
