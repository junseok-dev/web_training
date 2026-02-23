"""
Short-Cut v3.0 - Pinecone Serverless Vector Database
========================================================
Vector database interface for Pinecone with Hybrid Search.

Features:
- Pinecone Serverless for Dense + Sparse search
- Client-side Sparse Encoding (pinecone-text)
- RRF (Reciprocal Rank Fusion) support
- Batch upsert optimization

Author: Team 뀨💕
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
import pickle
import re
from collections import defaultdict
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from tqdm import tqdm

try:
    from pinecone import Pinecone, ServerlessSpec
    PINECONE_AVAILABLE = True
    from pinecone_text.sparse import BM25Encoder
except ImportError:
    PINECONE_AVAILABLE = False

from src.config import config, PineconeConfig, EMBEDDINGS_DIR, INDEX_DIR


# =============================================================================
# Logging Setup
# =============================================================================

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SearchResult:
    """Result from vector similarity search."""
    chunk_id: str
    patent_id: str
    score: float
    content: str
    content_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Hybrid search fields
    dense_score: float = 0.0
    sparse_score: float = 0.0
    rrf_score: float = 0.0



@dataclass
class InsertResult:
    """Result from inserting vectors."""
    success: bool
    inserted_count: int
    index_path: str
    error_message: Optional[str] = None


# =============================================================================
# Helper Functions
# =============================================================================

def compute_rrf(
    dense_results: List[SearchResult],
    sparse_results: List[Tuple[str, float, Dict[str, Any]]],
    dense_weight: float = 0.5,
    sparse_weight: float = 0.5,
    rrf_k: int = 60,
    top_k: int = 10,
) -> List[SearchResult]:
    """
    Compute Reciprocal Rank Fusion (RRF) scores.
    
    Args:
        dense_results: List of SearchResult objects from dense search
        sparse_results: List of (chunk_id, score, metadata) from sparse search
        dense_weight: Weight for dense search contribution
        sparse_weight: Weight for sparse search contribution
        rrf_k: RRF constant
        top_k: Number of results to return

    Returns:
        List of SearchResult objects sorted by RRF score
    """
    rrf_scores: Dict[str, float] = defaultdict(float)
    chunk_data: Dict[str, SearchResult] = {}
    
    # Process dense results
    for rank, result in enumerate(dense_results):
        rrf_scores[result.chunk_id] += dense_weight / (rrf_k + rank + 1)
        # Store original dense score
        result.dense_score = result.score
        chunk_data[result.chunk_id] = result
    
    # Process sparse results
    for rank, (chunk_id, score, meta) in enumerate(sparse_results):
        rrf_scores[chunk_id] += sparse_weight / (rrf_k + rank + 1)
        
        if chunk_id not in chunk_data:
            # Create SearchResult from BM25 result if found only in sparse
            chunk_data[chunk_id] = SearchResult(
                chunk_id=chunk_id,
                patent_id=meta.get("patent_id", ""),
                score=0.0,
                content=meta.get("content", ""),
                content_type=meta.get("content_type", ""),
                sparse_score=score,
                metadata={
                    "ipc_code": meta.get("ipc_code", ""),
                    "importance_score": meta.get("importance_score", 0.0),
                    "title": meta.get("title", ""),
                    "abstract": meta.get("abstract", ""),
                    "claims": meta.get("claims", ""),
                    # Ensure metadata is preserved
                    **{k: v for k, v in meta.items() if k not in ["content", "content_type", "patent_id", "title", "abstract", "claims"]}
                },
            )
        else:
            chunk_data[chunk_id].sparse_score = score
            
    # Sort by RRF score descending
    sorted_ids = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    
    final_results = []
    for chunk_id, rrf_score in sorted_ids[:top_k]:
        if chunk_id in chunk_data:
            result = chunk_data[chunk_id]
            result.rrf_score = rrf_score
            result.score = rrf_score  # Update main score to RRF
            final_results.append(result)
            
    return final_results





# =============================================================================
# Pinecone Client with Hybrid Search
# =============================================================================

class PineconeClient:
    """
    Pinecone-based vector database (Serverless) with Hybrid Search.
    
    Features:
    - Dense search using Pinecone (Serverless)
    - Sparse search using local BM25
    - RRF Fusion for result merging
    - Batch upsert logic
    """
    
    def __init__(
        self,
        pinecone_config: PineconeConfig = None,
        embedding_dim: int = None,
        skip_init_check: bool = False,
    ):
        if not PINECONE_AVAILABLE:
            raise ImportError("pinecone is required. Install with: pip install pinecone>=3.0.0")
        
        self.config = pinecone_config or config.pinecone
        self.embedding_dim = embedding_dim or config.embedding.embedding_dim
        
        # Initialize Pinecone
        if not self.config.api_key:
            raise ValueError("PINECONE_API_KEY not set")
            
        self.pc = Pinecone(api_key=self.config.api_key)
        
        # Ensure index exists (Auto-creation for reset scenarios)
        if not skip_init_check:
            self._ensure_index_exists()
            
        self.index = self.pc.Index(self.config.index_name)
        
        # Local metadata cache (Synchronized with FaissClient logic)
        self.metadata: Dict[str, Dict[str, Any]] = {}
        self.metadata_path = self.config.metadata_path or INDEX_DIR / "pinecone_metadata.pkl"
        
        # Setup BM25 Encoder (Serverless Hybrid)
        # We need to load fitted parameters if available, otherwise start new
        self.bm25_params_path = INDEX_DIR / "bm25_params.json"
        
        try:
            if self.bm25_params_path.exists():
                self.bm25_encoder = BM25Encoder().load(str(self.bm25_params_path))
                logger.info(f"Loaded BM25 params from {self.bm25_params_path}")
            else:
                self.bm25_encoder = BM25Encoder.default()
                logger.info("Initialized default BM25Encoder (will need fitting)")
        except Exception as e:
             logger.warning(f"Failed to load BM25 encoder: {e}. Using default.")
             self.bm25_encoder = BM25Encoder.default()

        logger.info(f"Pinecone Client initialized (index={self.config.index_name})")

    def _ensure_index_exists(self):
        """Check if index exists, create if not (Serverless)."""
        existing_indexes = [i.name for i in self.pc.list_indexes()]
        
        if self.config.index_name not in existing_indexes:
            logger.info(f"Creating Pinecone index '{self.config.index_name}'...")
            try:
                self.pc.create_index(
                    name=self.config.index_name,
                    dimension=self.config.dimension,
                    metric=self.config.metric,
                    spec=ServerlessSpec(
                        cloud=self.config.cloud,
                        region=self.config.region
                    )
                )
                logger.info(f"Index '{self.config.index_name}' created successfully")
            except Exception as e:
                logger.error(f"Failed to create Pinecone index: {e}")
                raise

    def add_vectors(
        self,
        embeddings: np.ndarray,
        metadata_list: List[Dict[str, Any]],
        normalize: bool = False,  # Pinecone cosine metric usually handles normalized vectors better, but check metric
    ) -> int:
        """
        Batch add vectors to Pinecone and update local BM25.
        """
        if normalize and self.config.metric == 'cosine':
             # Normalize embeddings to unit length for cosine similarity
             # (Though Pinecone 'cosine' does normalization automatically, it's safe to do valid L2 norm)
             pass 
             # Only strictly needed if metric is dotproduct acting as cosine
        
        total = len(embeddings)
        batch_size = self.config.batch_size
        
        logger.info(f"Upserting {total} vectors to Pinecone (batch_size={batch_size})...")

        # 1. Fit BM25 Encoder if needed (First time) - Ideally done before manual call, but here we can check
        # NOTE: BM25Encoder needs full corpus stats. In a batch scenario, we might be just adding.
        # Ideally, we fit on the *whole* corpus before. 
        # Here we assume the encoder is already reasonably fitted or we fit on this batch (suboptimal but works for cold start).
        
        # Collect all texts for sparse encoding
        all_texts = [m.get("content", "") for m in metadata_list]
        
        # If default/empty, we MUST fit.
        # A simple heuristic: check if doc_freq is empty
        if len(self.bm25_encoder.doc_freq) == 0:
             logger.info("Fitness check: Fitting BM25 encoder on new batch (Cold Start)...")
             self.bm25_encoder.fit(all_texts)
             # Save params immediately
             self.bm25_encoder.dump(str(self.bm25_params_path))
        
        # Generate Sparse Vectors for ALL documents in batch
        # (pinecone-text handles parallelization? or we loop)
        sparse_vectors = self.bm25_encoder.encode_documents(all_texts)
        
        upsert_count = 0
        from tqdm import tqdm
        
        for i in tqdm(range(0, total, batch_size), desc="Upserting to Pinecone", unit="batch"):
            batch_vectors = embeddings[i : i + batch_size]
            batch_meta = metadata_list[i : i + batch_size]
            batch_sparse = sparse_vectors[i : i + batch_size]
            
            vectors_to_upsert = []
            for j, (vec, meta, sparse) in enumerate(zip(batch_vectors, batch_meta, batch_sparse)):
                chunk_id = meta.get("chunk_id", f"chk_{i+j}")
                
                # Metadata Truncation Strategy
                content_text = meta.get("content", "")
                # Limit to 30KB text to be safe
                if len(content_text.encode('utf-8')) > 30000:
                    content_text = content_text[:10000]

                flat_meta = {
                    "text": content_text,
                    "title": (meta.get("title", "") or "")[:500],
                    "patent_id": meta.get("patent_id", ""),
                    "ipc_code": (meta.get("ipc_codes") or [""])[0] if isinstance(meta.get("ipc_codes"), list) else str(meta.get("ipc_codes", "")),
                    "abstract": (meta.get("abstract", "") or "")[:1000],
                    "claims": (meta.get("claims", "") or "")[:2000],
                    "importance_score": float(meta.get("importance_score", 0.0))
                }
                
                # Store in local metadata cache as well
                self.metadata[chunk_id] = meta
                
                vector_payload = {
                    "id": chunk_id,
                    "values": vec.tolist(),
                    "metadata": {k: v for k, v in flat_meta.items() if v} # Filter out empty values
                }
                
                # Only inject Sparse Vector if it has values (Pinecone requirement)
                if sparse.get("indices") is not None and len(sparse["indices"]) > 0:
                    vector_payload["sparse_values"] = sparse
                
                vectors_to_upsert.append(vector_payload)
            
            try:
                self.index.upsert(vectors=vectors_to_upsert, namespace=self.config.namespace)
                upsert_count += len(vectors_to_upsert)
            except Exception as e:
                logger.error(f"Pinecone upsert failed at batch {i}: {e}")
                raise e
        
        return upsert_count

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        normalize: bool = False, # Handled by Pinecone usually
        ipc_filters: List[str] = None,
    ) -> List[SearchResult]:
        """
        Dense search using Pinecone with optional IPC filtering.
        """
        if query_embedding.ndim > 1:
            query_embedding = query_embedding[0] # Take first if batch
            
        # If filtering, fetch more results to allow for filtering
        fetch_k = top_k * 5 if ipc_filters else top_k
            
        try:
            response = self.index.query(
                vector=query_embedding.tolist(),
                top_k=fetch_k,
                include_metadata=True,
                namespace=self.config.namespace
            )
        except Exception as e:
            logger.error(f"Pinecone search failed: {e}")
            return []
            
        results = []
        for match in response['matches']:
            meta = match['metadata'] if match.get('metadata') else {}
            chunk_id = match['id']
            score = match['score']
            
            # Local metadata might have more details (claims, etc)
            local_meta = self.metadata.get(chunk_id, {})
            
            # Prefer local metadata for full context if avail, else fallback to Pinecone meta
            final_meta = local_meta or meta
            ipc_code = final_meta.get("ipc_code", meta.get("ipc_code", ""))
            
            # Filter logic: Check if ipc_code starts with any of the filters
            if ipc_filters:
                # ipc_filters example: ['G06', 'H04']
                # ipc_code example: "G06Q 50/10"
                if not any(ipc_code.startswith(f) for f in ipc_filters):
                    continue
            
            content = local_meta.get("content") or meta.get("text", "")
            patent_id = local_meta.get("patent_id") or meta.get("patent_id", "")
            
            results.append(SearchResult(
                chunk_id=chunk_id,
                patent_id=patent_id,
                score=score,
                content=content,
                content_type=local_meta.get("content_type", "unknown"),
                dense_score=score,
                metadata=final_meta
            ))
            
            if len(results) >= top_k:
                break
                
        return results

    def hybrid_search(
        self,
        query_embedding: np.ndarray,
        query_text: str,
        top_k: int = 10,
        dense_weight: float = 0.5,
        sparse_weight: float = 0.5,
        ipc_filters: List[str] = None,
        rrf_k: int = 60,
        normalize: bool = True,
    ) -> List[SearchResult]:
        """
        Serverless Hybrid Search using Pinecone (Dense + Sparse).
        IPC Filtering is done client-side for prefix matching support.
        """
        # 0. Preparation
        if query_embedding.ndim > 1:
            query_embedding = query_embedding[0]
            
        # 1. Generate Query Vectors (Dense & Sparse)
        # Apply weights directly to vectors for weighted sum hybrid scoring
        weighted_dense = (query_embedding * dense_weight).tolist()
        
        # Sparse encoding
        sparse_vec = self.bm25_encoder.encode_queries(query_text)
        weighted_sparse = {
            "indices": sparse_vec["indices"],
            "values": [v * sparse_weight for v in sparse_vec["values"]]
        }
        
        # 2. Query Pinecone
        # Fetch more items to allow client-side filtering (Prefix match on IPC)
        fetch_k = top_k * 5 if ipc_filters else top_k
        
        try:
            # Prepare query args
            query_args = {
                "vector": weighted_dense,
                "top_k": fetch_k,
                "include_metadata": True,
                "namespace": self.config.namespace
            }
            
            # Only add sparse_vector if it has values (Pinecone requirement)
            if weighted_sparse.get("indices") is not None and len(weighted_sparse["indices"]) > 0:
                query_args["sparse_vector"] = weighted_sparse
            
            response = self.index.query(**query_args)
        except Exception as e:
            logger.error(f"Pinecone hybrid query failed: {e}")
            return []
            
        # 3. Process Results (Mapping & Filtering)
        results = []
        for match in response['matches']:
            meta = match['metadata'] if match.get('metadata') else {}
            score = match['score']
            
            # Extract basic fields
            chunk_id = match['id']
            ipc_code = meta.get("ipc_code", "")
            
            # Client-side IPC Filtering (Prefix Match)
            if ipc_filters:
                # ipc_filters example: ['G06', 'H04']
                if not any(ipc_code.startswith(f) for f in ipc_filters):
                    continue
            
            results.append(SearchResult(
                chunk_id=chunk_id,
                patent_id=meta.get("patent_id", ""),
                score=score,
                content=meta.get("text", ""), # Content served from Pinecone metadata
                content_type="text",
                dense_score=score, # Pinecone hybrid score
                metadata=meta
            ))
            
            if len(results) >= top_k:
                break
        
        logger.info(f"Pinecone Hybrid Search(IPC={ipc_filters}): Found {len(results)} matches")
        return results

    def fetch_by_ids(self, patent_ids: List[str]) -> List[SearchResult]:
        """
        Fetch specific patents by their publication numbers/IDs.
        Uses Pinecone's fetch or query with filter.
        """
        if not patent_ids:
            return []
            
        logger.info(f"Fetching specific patents: {patent_ids}")
        
        try:
            # We use query with filter because patent_id is a metadata field
            # and may not be the same as chunk_id (vector ID).
            # One patent can have multiple chunks.
            
            # Note: Serverless Pinecone supports metadata filtering
            filter_dict = {"patent_id": {"$in": patent_ids}}
            
            # Since we want to find the most relevant chunk for each patent
            # but we don't have a query embedding, we'll just fetch a few chunks per patent.
            # Usually, the first chunk of a patent contains the title/abstract/claims.
            
            response = self.index.query(
                vector=[0.0] * self.embedding_dim, # Dummy vector for metadata-only filtering
                filter=filter_dict,
                top_k=20, # Fetch up to 20 chunks total across these patents
                include_metadata=True,
                namespace=self.config.namespace
            )
            
            results = []
            seen_patents = set()
            
            for match in response['matches']:
                meta = match['metadata'] if match.get('metadata') else {}
                p_id = meta.get("patent_id", "")
                
                # Take only the first chunk we find for each requested patent to keep it clean
                if p_id in patent_ids and p_id not in seen_patents:
                    seen_patents.add(p_id)
                    chunk_id = match['id']
                    
                    # Local metadata might have more details
                    local_meta = self.metadata.get(chunk_id, {})
                    final_meta = local_meta or meta
                    
                    content = local_meta.get("content") or meta.get("text", "")
                    
                    results.append(SearchResult(
                        chunk_id=chunk_id,
                        patent_id=p_id,
                        score=1.0, # Target match booster
                        content=content,
                        content_type=local_meta.get("content_type", "unknown"),
                        dense_score=1.0,
                        metadata=final_meta
                    ))
            
            return results
            
        except Exception as e:
            logger.error(f"Pinecone fetch_by_ids failed: {e}")
            return []

    async def async_fetch_by_ids(self, *args, **kwargs):
        """Async wrapper."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.fetch_by_ids(*args, **kwargs))

    async def async_search(self, *args, **kwargs):
        """Async wrapper."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.search(*args, **kwargs))

    async def async_hybrid_search(self, *args, **kwargs):
        """Async wrapper."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.hybrid_search(*args, **kwargs))

    def save_local(self) -> None:
        """Save BM25 parameters and metadata cache."""
        # Save BM25 Params
        self.bm25_params_path.parent.mkdir(parents=True, exist_ok=True)
        self.bm25_encoder.dump(str(self.bm25_params_path))
        logger.info(f"Saved BM25 params to {self.bm25_params_path}")
        
        # Save Metadata Cache
        with open(self.metadata_path, 'wb') as f:
            pickle.dump({"metadata": self.metadata}, f)
        logger.info(f"Saved metadata cache to {self.metadata_path}")

    def load_local(self) -> bool:
        """Load BM25 parameters and metadata cache."""
        success = True
        
        # 1. Load BM25
        if self.bm25_params_path.exists():
            try:
                self.bm25_encoder = BM25Encoder().load(str(self.bm25_params_path))
                logger.info(f"Loaded BM25 params from {self.bm25_params_path}")
            except Exception as e:
                logger.error(f"Failed to load BM25 params: {e}")
                success = False
        else:
            success = False
            
        # 2. Load Metadata
        if self.metadata_path.exists():
            try:
                with open(self.metadata_path, 'rb') as f:
                    data = pickle.load(f)
                    self.metadata = data.get("metadata", {})
                logger.info(f"Loaded metadata cache from {self.metadata_path} ({len(self.metadata)} items)")
            except Exception as e:
                logger.error(f"Failed to load metadata cache: {e}")
                success = False
        
        self._loaded = success
        return success

    def get_stats(self) -> Dict[str, Any]:
        """Get index stats."""
        try:
            stats = self.index.describe_index_stats()
            # Try to get doc_count from encoder if possible (avg_doc_len usually present)
            bm25_status = "initialized" if hasattr(self.bm25_encoder, 'doc_freq') and len(self.bm25_encoder.doc_freq) > 0 else "empty"
            
            return {
                "type": "pinecone", 
                "total_vectors": stats.get('total_vector_count', 0),
                "bm25_status": bm25_status
            }
        except:
            return {"type": "pinecone", "error": "stats_failed"}


# =============================================================================
# Keyword Extractor
# =============================================================================

class KeywordExtractor:
    """
    Extract keywords from query text for BM25 search.
    """
    
    # Common stop words to filter out
    STOP_WORDS = {
        'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
        'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as',
        'into', 'through', 'during', 'before', 'after', 'above', 'below',
        'between', 'under', 'again', 'further', 'then', 'once', 'here',
        'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few',
        'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
        'own', 'same', 'so', 'than', 'too', 'very', 'just', 'and', 'but',
        'if', 'or', 'because', 'until', 'while', 'this', 'that', 'these',
        'those', 'what', 'which', 'who', 'whom', 'whose',
    }
    
    # Technical terms to boost
    TECHNICAL_TERMS = {
        'method', 'system', 'apparatus', 'device', 'process', 'machine',
        'algorithm', 'model', 'network', 'layer', 'module', 'component',
        'database', 'index', 'vector', 'embedding', 'retrieval', 'search',
        'query', 'document', 'text', 'language', 'neural', 'learning',
        'training', 'inference', 'classification', 'clustering', 'ranking',
        'generation', 'processing', 'analysis', 'extraction', 'recognition',
    }
    
    @classmethod
    def extract(cls, text: str, max_keywords: int = 20) -> List[str]:
        """
        Extract keywords from text.
        
        Args:
            text: Input text
            max_keywords: Maximum number of keywords to return
            
        Returns:
            List of keywords sorted by importance
        """
        if not text:
            return []
        
        # Tokenize
        words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9]*\b', text.lower())
        
        # Filter stop words and short words
        filtered = [w for w in words if w not in cls.STOP_WORDS and len(w) > 2]
        
        # Count frequency
        word_freq = defaultdict(int)
        for word in filtered:
            word_freq[word] += 1
        
        # Score words (frequency + technical term boost)
        scored = []
        for word, freq in word_freq.items():
            score = freq
            if word in cls.TECHNICAL_TERMS:
                score *= 2  # Boost technical terms
            scored.append((word, score))
        
        # Sort by score
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return [word for word, _ in scored[:max_keywords]]


# =============================================================================
# High-Level Operations
# =============================================================================



# =============================================================================
# CLI Entry Point
# =============================================================================

async def main():
    """Test Pinecone Hybrid Search."""
    logging.basicConfig(
        level=logging.INFO,
        format=config.logging.log_format,
    )
    
    print("\n" + "=" * 70)
    print("⚡ 쇼특허 (Short-Cut) v3.0 - Pinecone Hybrid Search Test")
    print("=" * 70)
    
    if not PINECONE_AVAILABLE:
        print("❌ pinecone-client not installed.")
        return

    # Initialize client
    try:
        client = PineconeClient(skip_init_check=True)
    except Exception as e:
        print(f"❌ Failed to init PineconeClient: {e}")
        return
    
    stats = client.get_stats()
    print(f"📊 Index stats: {stats}")
    
    if stats.get("total_vectors", 0) == 0:
        print("ℹ️ Index is empty. Upsert data first using the pipeline.")
        return

    # Test hybrid search
    query_text = "neural network semantic search"
    # Create random embedding for test
    query_embedding = np.random.randn(1536).astype(np.float32)

    print(f"\n🔍 Testing hybrid search for: '{query_text}'")
    
    results = client.hybrid_search(
        query_embedding=query_embedding, 
        query_text=query_text, 
        top_k=5
    )
    
    print(f"   Found: {len(results)} results")
    for r in results:
        print(f"   - {r.patent_id}: {r.score:.4f} (IPC: {r.metadata.get('ipc_code', 'N/A')})")
    
    print("\n" + "=" * 70)
    print("✅ Test complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
