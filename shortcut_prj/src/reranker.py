"""
Reranker Module - Re-ranking search results using Cross-Encoder.
"""
import logging
from typing import List, Dict, Any
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)

# Default model (lightweight, good performance)
MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

class Reranker:
    def __init__(self, model_name: str = MODEL_NAME):
        self.model = None
        self.model_name = model_name
        self._load_model()
        
    def _load_model(self):
        """Lazy load the model."""
        try:
            from sentence_transformers import CrossEncoder
            import torch
            
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading Reranker model {self.model_name} on {device}...")
            
            self.model = CrossEncoder(self.model_name, device=device)
            logger.info("Reranker model loaded successfully.")
            
        except ImportError:
            logger.warning("sentence-transformers not installed. Reranking disabled.")
        except Exception as e:
            logger.error(f"Failed to load Reranker model: {e}")

    def rerank(
        self, 
        query: str, 
        docs: List[Dict[str, Any]], 
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Rerank a list of documents based on query relevance.
        
        Args:
            query: User query
            docs: List of document dicts (must have 'content' or 'abstract')
            top_k: Number of results to return
            
        Returns:
            Reranked list of documents with 'rerank_score'
        """
        if not self.model or not docs:
            return docs[:top_k]
            
        # Prepare pairs for cross-encoder
        # (Query, Document Title + Abstract) usually works best
        pairs = []
        for doc in docs:
            # Construct text representation for reranking
            # Use title + abstract + claims (if short)
            text = f"{doc.get('title', '')} {doc.get('abstract', '')}"
            
            # If text is too long, truncate? Model handles max_length usually (512 tokens)
            pairs.append([query, text[:1000]])
            
        try:
            # Predict scores
            scores = self.model.predict(pairs)
            
            # Add scores to docs
            for doc, score in zip(docs, scores):
                doc['rerank_score'] = float(score)
                
            # Sort by new score
            docs.sort(key=lambda x: x.get('rerank_score', 0), reverse=True)
            
            logger.info(f"Reranked {len(docs)} documents.")
            return docs[:top_k]
            
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return docs[:top_k]
