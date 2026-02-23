"""
Short-Cut - OpenAI API Embedder (Antigravity Edition)
==============================================================
Lightweight embedding generation using OpenAI text-embedding-3-small.

No local models, no GPU required - pure API-based embeddings.

Author: Team 뀨💕
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import numpy as np
from tqdm import tqdm
from openai import AsyncOpenAI

from src.config import config, EmbeddingConfig


# =============================================================================
# Logging Setup
# =============================================================================

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class EmbeddingResult:
    """Result of embedding generation."""
    text_id: str
    embedding: np.ndarray
    content_type: str  # "title", "abstract", "claim", "description"
    weight: float = 1.0
    metadata: Dict[str, Any] = None


# =============================================================================
# OpenAI Embedder
# =============================================================================

class OpenAIEmbedder:
    """
    Generate embeddings using OpenAI API.
    
    Features:
    - Async batch processing for efficiency
    - Automatic rate limiting
    - Content-type based weighting
    """
    
    def __init__(
        self,
        embedding_config: EmbeddingConfig = config.embedding,
    ):
        self.config = embedding_config
        
        if not self.config.api_key:
            raise ValueError("OPENAI_API_KEY not set. Check .env file or config.")
        
        self.client = AsyncOpenAI(api_key=self.config.api_key)
        
        logger.info(f"OpenAI Embedder initialized with model: {self.config.model_id}")
    
    def _get_weight(self, content_type: str) -> float:
        """Get weight for content type."""
        weights = {
            "title": self.config.title_weight,
            "claim": self.config.claim_weight,
            "abstract": self.config.abstract_weight,
            "description": self.config.description_weight,
        }
        return weights.get(content_type, 1.0)
    
    async def embed_text(
        self,
        text: str,
        text_id: str = "",
        content_type: str = "description",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EmbeddingResult:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            text_id: Unique identifier
            content_type: Type of content for weight assignment
            metadata: Optional metadata to attach
            
        Returns:
            EmbeddingResult with embedding and metadata
        """
        # Truncate text if needed
        if len(text) > self.config.max_context_length * 4:  # Rough estimate: 4 chars per token
            text = text[:self.config.max_context_length * 4]
        
        response = await self.client.embeddings.create(
            model=self.config.model_id,
            input=text,
        )
        
        embedding = np.array(response.data[0].embedding, dtype=np.float32)
        
        return EmbeddingResult(
            text_id=text_id,
            embedding=embedding,
            content_type=content_type,
            weight=self._get_weight(content_type),
            metadata=metadata or {},
        )
    
    async def embed_batch(
        self,
        items: List[Dict[str, Any]],
        text_key: str = "text",
        id_key: str = "id",
        type_key: str = "type",
        show_progress: bool = True,
    ) -> List[EmbeddingResult]:
        """
        Generate embeddings for a batch of items using OpenAI batch API.
        
        Args:
            items: List of dicts with text and metadata
            text_key: Key for text content in items
            id_key: Key for item ID
            type_key: Key for content type
            show_progress: Show progress bar
            
        Returns:
            List of EmbeddingResult objects
        """
        results = []
        batch_size = min(self.config.batch_size, 2048)  # OpenAI limit
        
        # Process in batches
        total_batches = (len(items) + batch_size - 1) // batch_size
        
        iterator = range(0, len(items), batch_size)
        if show_progress:
            iterator = tqdm(iterator, desc="Embedding", unit="batch", total=total_batches)
        
        for i in iterator:
            batch_items = items[i:i + batch_size]
            
            # Prepare texts (truncate if needed)
            batch_texts = []
            for item in batch_items:
                text = item.get(text_key, "")
                if len(text) > self.config.max_context_length * 4:
                    text = text[:self.config.max_context_length * 4]
                batch_texts.append(text)
            
            # Call OpenAI API
            try:
                response = await self.client.embeddings.create(
                    model=self.config.model_id,
                    input=batch_texts,
                )
                
                # Process results
                for j, item in enumerate(batch_items):
                    content_type = item.get(type_key, "description")
                    embedding = np.array(response.data[j].embedding, dtype=np.float32)
                    
                    results.append(EmbeddingResult(
                        text_id=item.get(id_key, f"item_{i+j}"),
                        embedding=embedding,
                        content_type=content_type,
                        weight=self._get_weight(content_type),
                        metadata={k: v for k, v in item.items() 
                                  if k not in [text_key, id_key, type_key]},
                    ))
                    
            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                # Add empty embeddings for failed items
                for j, item in enumerate(batch_items):
                    results.append(EmbeddingResult(
                        text_id=item.get(id_key, f"item_{i+j}"),
                        embedding=np.zeros(self.config.embedding_dim, dtype=np.float32),
                        content_type=item.get(type_key, "description"),
                        weight=1.0,
                        metadata={"error": str(e)},
                    ))
            
            # Small delay to respect rate limits
            if i + batch_size < len(items):
                await asyncio.sleep(0.1)
        
        return results
    
    async def embed_patent_chunks(
        self,
        chunks: List[Dict[str, Any]],
        show_progress: bool = True,
    ) -> List[EmbeddingResult]:
        """
        Generate embeddings for patent chunks with appropriate weights.
        
        Args:
            chunks: List of PatentChunk-like dicts
            show_progress: Show progress bar
            
        Returns:
            List of EmbeddingResult objects
        """
        # Convert chunks to embedding input format
        items = []
        for chunk in chunks:
            chunk_type = chunk.get("chunk_type", "description")
            
            # Map chunk types to content types
            content_type_map = {
                "parent": "abstract",
                "abstract": "abstract",
                "claim": "claim",
                "description_section": "description",
            }
            content_type = content_type_map.get(chunk_type, "description")
            
            items.append({
                "text": chunk.get("content", ""),
                "id": chunk.get("chunk_id", ""),
                "type": content_type,
                "patent_id": chunk.get("patent_id"),
                "chunk_type": chunk_type,
                "metadata": chunk.get("metadata", {}),
            })
        
        return await self.embed_batch(
            items,
            text_key="text",
            id_key="id",
            type_key="type",
            show_progress=show_progress,
        )


# =============================================================================
# Backward Compatibility Alias
# =============================================================================

PatentEmbedder = OpenAIEmbedder


# =============================================================================
# CLI Entry Point
# =============================================================================

async def main():
    """Test embedding generation."""
    logging.basicConfig(
        level=logging.INFO,
        format=config.logging.log_format,
    )
    
    print("\n" + "=" * 70)
    print("⚡ 쇼특허 (Short-Cut) - OpenAI Embedder Test")
    print(f"   Model: {config.embedding.model_id}")
    print(f"   Dimension: {config.embedding.embedding_dim}")
    print("=" * 70)
    
    # Test texts
    test_texts = [
        {
            "id": "test_title",
            "type": "title",
            "text": "Method for Retrieval-Augmented Generation in Patent Search",
        },
        {
            "id": "test_claim",
            "type": "claim",
            "text": """A computer-implemented method for semantic patent search comprising:
                receiving a query describing a technical concept;
                generating a dense vector embedding of the query;
                retrieving relevant patent documents from a vector database;
                synthesizing a response using a language model.""",
        },
        {
            "id": "test_abstract",
            "type": "abstract",
            "text": """This invention relates to an improved method for searching prior art 
                using retrieval-augmented generation techniques. The system combines 
                dense vector retrieval with large language model inference to provide 
                accurate and contextually relevant patent search results.""",
        },
    ]
    
    # Initialize embedder
    embedder = OpenAIEmbedder()
    
    print("\n📊 Generating embeddings...")
    results = await embedder.embed_batch(test_texts, show_progress=False)
    
    print("\n✅ Results:")
    for result in results:
        print(f"\n   ID: {result.text_id}")
        print(f"   Type: {result.content_type}")
        print(f"   Weight: {result.weight}")
        print(f"   Shape: {result.embedding.shape}")
        print(f"   L2 Norm: {np.linalg.norm(result.embedding):.4f}")
    
    # Compute similarities
    print("\n📐 Pairwise Similarities:")
    from scipy.spatial.distance import cosine
    for i, r1 in enumerate(results):
        for j, r2 in enumerate(results):
            if i < j:
                sim = 1 - cosine(r1.embedding, r2.embedding)
                print(f"   {r1.text_id} <-> {r2.text_id}: {sim:.4f}")
    
    print("\n" + "=" * 70)
    print("✅ OpenAI Embedding test complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
