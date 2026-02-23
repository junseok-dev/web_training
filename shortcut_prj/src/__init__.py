"""
Short-Cut - Source Package
===================================
RAG and sLLM domain-specialized prior art search system.

Modules:
- config: Central configuration management
- bigquery_extractor: Google Patents data extraction
- preprocessor: Claim parsing and hierarchical chunking
- triplet_generator: PAI-NET triplet generation
- embedder: Intel XPU optimized embedding
- vector_db: Milvus vector database operations
- self_rag_generator: Self-RAG training data generation
- pipeline: Main orchestration pipeline

Author: Team 뀨💕
License: MIT
"""

from .config import config, PatentGuardConfig

__version__ = "2.0.0"
__all__ = [
    "config",
    "PatentGuardConfig",
]
