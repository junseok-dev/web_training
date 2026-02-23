"""
Short-Cut - Main Pipeline Orchestrator (Antigravity Edition)
=====================================================================
Orchestrates the complete patent data pipeline.

Pipeline stages:
1. BigQuery extraction
2. Preprocessing & chunking
3. PAI-NET triplet generation (optional)
4. Embedding generation (OpenAI API)
5. Pinecone Vector Indexing (Serverless)
6. Self-RAG training data generation (optional)

Author: Team 뀨💕
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from datetime import datetime
from typing import Optional

# Use orjson for faster JSON I/O
try:
    import orjson
    def json_load(f): return orjson.loads(f.read())
    def json_dump(obj, f): f.write(orjson.dumps(obj, option=orjson.OPT_INDENT_2))
except ImportError:
    import json
    def json_load(f): return json.load(f)
    def json_dump(obj, f): json.dump(obj, f, ensure_ascii=False, indent=2)

import numpy as np

from src.config import (
    config,
    print_config_summary,
    update_config_from_env,
    RAW_DATA_DIR,
    PROCESSED_DATA_DIR,
    TRIPLETS_DIR,
    EMBEDDINGS_DIR,
    INDEX_DIR,
)

# =============================================================================
# Logging Setup  
# =============================================================================

def setup_logging() -> logging.Logger:
    """Configure logging for the pipeline."""
    logging.basicConfig(
        level=getattr(logging, config.logging.log_level),
        format=config.logging.log_format,
        handlers=[
            logging.StreamHandler(),
        ],
    )
    
    if config.logging.log_file:
        file_handler = logging.FileHandler(config.logging.log_file)
        file_handler.setFormatter(logging.Formatter(config.logging.log_format))
        logging.getLogger().addHandler(file_handler)
    
    return logging.getLogger(__name__)


logger = setup_logging()


# =============================================================================
# Pipeline Stages
# =============================================================================

async def stage_1_extraction(
    limit: Optional[int] = None,
    dry_run: bool = True,
) -> Optional[Path]:
    """
    Stage 1: Extract patent data from BigQuery.
    
    Returns:
        Path to extracted data file, or None if dry run
    """
    from src.bigquery_extractor import BigQueryExtractor
    
    print("\n" + "=" * 70)
    print("📥 Stage 1: BigQuery Data Extraction")
    print("=" * 70)
    
    # Update config for dry run
    config.bigquery.dry_run = dry_run
    
    extractor = BigQueryExtractor()
    result = await extractor.extract_patents(limit=limit)
    
    if result.success:
        print(f"✅ Extraction complete: {result.patents_count} patents")
        if result.cost_estimate:
            print(f"   {result.cost_estimate}")
        return result.output_path
    else:
        print(f"❌ Extraction failed: {result.error_message}")
        return None


async def stage_2_preprocessing(
    input_path: Path,
) -> Optional[Path]:
    """
    Stage 2: Preprocess patents with claim parsing and chunking.
    
    Uses ProcessPoolExecutor with limited workers for CPU efficiency.
    
    Returns:
        Path to processed data file
    """
    from src.preprocessor import PatentPreprocessor
    
    print("\n" + "=" * 70)
    print("🔧 Stage 2: Patent Preprocessing")
    print(f"   Max Workers: {config.pipeline.max_workers}")
    print("=" * 70)
    
    # Load raw data
    with open(input_path, 'rb') as f:
        raw_patents = json_load(f)
    
    print(f"📂 Loaded {len(raw_patents)} raw patents")
    
    preprocessor = PatentPreprocessor()
    
    output_path = PROCESSED_DATA_DIR / f"processed_{input_path.stem}.json"
    processed = await preprocessor.process_patents_batch(raw_patents, output_path)
    
    total_claims = sum(len(p.claims) for p in processed)
    total_chunks = sum(len(p.chunks) for p in processed)
    
    print(f"✅ Preprocessing complete:")
    print(f"   Patents: {len(processed)}")
    print(f"   Claims: {total_claims}")
    print(f"   Chunks: {total_chunks}")
    
    return output_path


async def stage_3_triplet_generation(
    input_path: Path,
) -> Optional[Path]:
    """
    Stage 3: Generate PAI-NET triplets from citation relationships.
    
    Returns:
        Path to triplets file
    """
    from src.triplet_generator import PAINETTripletGenerator
    
    print("\n" + "=" * 70)
    print("🔗 Stage 3: PAI-NET Triplet Generation")
    print("=" * 70)
    
    # Load processed data
    with open(input_path, 'rb') as f:
        processed_patents = json_load(f)
    
    print(f"📂 Loaded {len(processed_patents)} processed patents")
    
    generator = PAINETTripletGenerator()
    generator.build_graph(processed_patents, text_field="abstract")
    
    output_path = TRIPLETS_DIR / f"triplets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    dataset = await generator.generate_triplets(output_path)
    
    print(f"✅ Triplet generation complete:")
    print(f"   Triplets: {dataset.total_triplets}")
    print(f"   Unique anchors: {dataset.unique_anchors}")
    print(f"   Hard negative ratio: {dataset.hard_negative_ratio:.2%}")
    
    return output_path


async def stage_4_embedding(
    input_path: Path,
) -> Optional[Path]:
    """
    Stage 4: Generate embeddings using OpenAI API.
    
    Returns:
        Path to embeddings file
    """
    from src.embedder import OpenAIEmbedder
    
    print("\n" + "=" * 70)
    print("🧠 Stage 4: Embedding Generation (OpenAI API)")
    print(f"   Model: {config.embedding.model_id}")
    print(f"   Dimension: {config.embedding.embedding_dim}")
    print("=" * 70)
    
    # Load processed data
    with open(input_path, 'rb') as f:
        processed_patents = json_load(f)
    
    # Extract all chunks
    all_chunks = []
    for patent in processed_patents:
        for chunk in patent.get("chunks", []):
            all_chunks.append(chunk)
    
    print(f"📂 Total chunks to embed: {len(all_chunks)}")
    
    # Initialize embedder
    embedder = OpenAIEmbedder()
    
    # Generate embeddings
    results = await embedder.embed_patent_chunks(all_chunks)
    
    # Save embeddings
    output_path = EMBEDDINGS_DIR / f"embeddings_{input_path.stem}.npz"
    
    embeddings = np.array([r.embedding for r in results])
    chunk_ids = [r.text_id for r in results]
    
    np.savez(
        output_path,
        embeddings=embeddings,
        chunk_ids=chunk_ids,
    )
    
    print(f"✅ Embedding generation complete:")
    print(f"   Embeddings: {len(results)}")
    print(f"   Shape: {embeddings.shape}")
    print(f"   Output: {output_path}")
    
    return output_path


async def stage_5_vector_indexing(
    processed_path: Path,
    embeddings_path: Path,
) -> bool:
    """
    Stage 5: Upload vectors to Pinecone (Migration).
    
    This uploads pre-computed embeddings to Pinecone Serverless index.
    
    Returns:
        True if successful
    """
    from src.vector_db import PineconeClient
    
    print("\n" + "=" * 70)
    print("🗄️  Stage 5: Pinecone Vector Indexing (Serverless)")
    print(f"   Index Name: {config.pinecone.index_name}")
    print("=" * 70)
    
    # Load data
    with open(processed_path, 'rb') as f:
        processed_patents = json_load(f)
    
    data = np.load(embeddings_path)
    embeddings = data['embeddings']
    chunk_ids = data['chunk_ids'].tolist()
    
    print(f"📂 Loaded {len(embeddings)} embeddings")
    
    # Build chunk lookup with full patent metadata
    chunk_lookup = {}
    for patent in processed_patents:
        patent_id = patent.get("publication_number", "")
        title = patent.get("title", "")
        abstract = patent.get("abstract", "")
        ipc_codes = patent.get("ipc_codes", [])
        importance_score = patent.get("importance_score", 0.0)
        
        # Get claims text
        claims = patent.get("claims", [])
        claims_text = ""
        if claims and isinstance(claims[0], dict):
            claims_text = claims[0].get("claim_text", "")
        
        for chunk in patent.get("chunks", []):
            chunk_id = chunk.get("chunk_id", "")
            chunk_lookup[chunk_id] = {
                "chunk_id": chunk_id,
                "patent_id": patent_id,
                "content": chunk.get("content", ""),
                "content_type": chunk.get("chunk_type", "description"),
                "ipc_code": (ipc_codes[0] if ipc_codes else "")[:20],
                "importance_score": importance_score,
                "weight": 1.0,
                "title": title,
                "abstract": abstract[:500] if abstract else "",
                "claims": claims_text[:1000] if claims_text else "",
            }
    
    # Prepare metadata for each embedding
    metadata_list = []
    for cid in chunk_ids:
        if cid in chunk_lookup:
            metadata_list.append(chunk_lookup[cid])
        else:
            metadata_list.append({
                "chunk_id": cid,
                "patent_id": "",
                "content": "",
                "content_type": "unknown",
            })
    
    # Initialize Pinecone client
    client = PineconeClient()
    
    # Add vectors (Upsert to Pinecone)
    # Note: This will also build local BM25 index
    added_count = client.add_vectors(embeddings, metadata_list)
    
    if added_count > 0:
        # Save local cache (BM25 + Metadata)
        client.save_local()
        
        try:
            stats = client.get_stats()
            print(f"✅ Pinecone indexing complete:")
            print(f"   Upserted vectors: {added_count}")
            print(f"   Total vectors in index: {stats.get('total_vectors', 'N/A')}")
            print(f"   Local cache saved to: {INDEX_DIR}")
            return True
        except Exception as e:
            print(f"✅ Indexing likely succeeded, but stats failed: {e}")
            return True
    else:
        print("❌ Indexing failed: No vectors added")
        return False


async def stage_6_selfrag_generation(
    input_path: Path,
) -> Optional[Path]:
    """
    Stage 6: Generate Self-RAG training data using OpenAI.
    
    Returns:
        Path to training data file
    """
    from src.self_rag_generator import SelfRAGDataGenerator
    
    print("\n" + "=" * 70)
    print("📝 Stage 6: Self-RAG Training Data Generation")
    print("=" * 70)
    
    if not config.self_rag.openai_api_key:
        print("⚠️  OPENAI_API_KEY not set. Skipping...")
        return None
    
    # Load processed data
    with open(input_path, 'rb') as f:
        processed_patents = json_load(f)
    
    print(f"📂 Loaded {len(processed_patents)} processed patents")
    
    generator = SelfRAGDataGenerator()
    
    output_path = PROCESSED_DATA_DIR / f"selfrag_training_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    samples = await generator.generate_training_samples(
        processed_patents,
        output_path,
    )
    
    print(f"✅ Self-RAG data generation complete:")
    print(f"   Samples: {len(samples)}")
    
    return output_path


# =============================================================================
# Full Pipeline
# =============================================================================

async def run_full_pipeline(
    extraction_limit: Optional[int] = 100,
    dry_run: bool = True,
    skip_stages: Optional[list] = None,
) -> None:
    """
    Run the complete patent data pipeline.
    
    Args:
        extraction_limit: Limit patents for testing
        dry_run: If True, only estimate BigQuery cost
        skip_stages: List of stage numbers to skip (1-6)
    """
    skip_stages = skip_stages or []
    
    print("\n" + "=" * 70)
    print("⚡ 쇼특허 (Short-Cut) - Full Pipeline (Antigravity Edition)")
    print("=" * 70)
    
    # Update config from environment
    update_config_from_env()
    print_config_summary()
    
    # Track outputs
    raw_data_path = None
    processed_path = None
    triplets_path = None
    embeddings_path = None
    selfrag_path = None
    
    try:
        # Stage 1: Extraction
        if 1 not in skip_stages:
            raw_data_path = await stage_1_extraction(
                limit=extraction_limit,
                dry_run=dry_run,
            )
            
            if not raw_data_path and not dry_run:
                print("❌ Pipeline stopped: Extraction failed")
                return
        else:
            # Look for existing raw data
            raw_files = list(RAW_DATA_DIR.glob("patents_*.json"))
            if raw_files:
                raw_data_path = max(raw_files, key=lambda p: p.stat().st_mtime)
                print(f"📂 Using existing raw data: {raw_data_path}")
        
        if dry_run:
            print("\n📊 Dry run complete. Set dry_run=False to execute.")
            return
        
        # Stage 2: Preprocessing
        if 2 not in skip_stages and raw_data_path:
            processed_path = await stage_2_preprocessing(raw_data_path)
        else:
            processed_files = list(PROCESSED_DATA_DIR.glob("processed_*.json"))
            if processed_files:
                processed_path = max(processed_files, key=lambda p: p.stat().st_mtime)
                print(f"📂 Using existing processed data: {processed_path}")
        
        # Stage 3: Triplet Generation (optional)
        if 3 not in skip_stages and processed_path:
            triplets_path = await stage_3_triplet_generation(processed_path)
        
        # Stage 4: Embedding Generation
        if 4 not in skip_stages and processed_path:
            embeddings_path = await stage_4_embedding(processed_path)
        else:
            # Look for existing embeddings
            embed_files = list(EMBEDDINGS_DIR.glob("embeddings_*.npz"))
            if embed_files:
                embeddings_path = max(embed_files, key=lambda p: p.stat().st_mtime)
                print(f"📂 Using existing embeddings: {embeddings_path}")
        
        # Stage 5: FAISS Indexing (Pre-computation)
        if 5 not in skip_stages and processed_path and embeddings_path:
            await stage_5_vector_indexing(processed_path, embeddings_path)
        
        # Stage 6: Self-RAG Training Data (optional)
        if 6 not in skip_stages and processed_path:
            selfrag_path = await stage_6_selfrag_generation(processed_path)
        
        # Summary
        print("\n" + "=" * 70)
        print("✅ Pipeline Execution Complete!")
        print("=" * 70)
        print("\n📁 Output Files:")
        if raw_data_path:
            print(f"   Raw Data: {raw_data_path}")
        if processed_path:
            print(f"   Processed: {processed_path}")
        if triplets_path:
            print(f"   Triplets: {triplets_path}")
        if embeddings_path:
            print(f"   Embeddings: {embeddings_path}")

        if selfrag_path:
            print(f"   Self-RAG: {selfrag_path}")
        
    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        print(f"\n❌ Pipeline failed: {e}")


# =============================================================================
# CLI Entry Points
# =============================================================================

async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Short-Cut v3.0 - Patent Data Pipeline (Antigravity Mode)"
    )
    
    parser.add_argument(
        "--stage",
        type=int,
        choices=[1, 2, 3, 4, 5, 6],
        help="Run specific stage only",
    )
    
    parser.add_argument(
        "--skip",
        type=int,
        nargs="*",
        default=[],
        help="Stages to skip (e.g., --skip 3 6)",
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Limit patents for extraction (default: 100)",
    )
    
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute BigQuery (not dry run)",
    )
    
    parser.add_argument(
        "--input",
        type=str,
        help="Input file for specific stage",
    )
    
    args = parser.parse_args()
    
    if args.stage:
        # Run specific stage
        input_path = Path(args.input) if args.input else None
        
        if args.stage == 1:
            await stage_1_extraction(limit=args.limit, dry_run=not args.execute)
        elif args.stage == 2:
            if not input_path:
                raw_files = list(RAW_DATA_DIR.glob("patents_*.json"))
                input_path = max(raw_files, key=lambda p: p.stat().st_mtime) if raw_files else None
            if input_path:
                await stage_2_preprocessing(input_path)
        elif args.stage == 3:
            if not input_path:
                proc_files = list(PROCESSED_DATA_DIR.glob("processed_*.json"))
                input_path = max(proc_files, key=lambda p: p.stat().st_mtime) if proc_files else None
            if input_path:
                await stage_3_triplet_generation(input_path)
        elif args.stage == 4:
            if not input_path:
                proc_files = list(PROCESSED_DATA_DIR.glob("processed_*.json"))
                input_path = max(proc_files, key=lambda p: p.stat().st_mtime) if proc_files else None
            if input_path:
                await stage_4_embedding(input_path)
        elif args.stage == 5:
            # Find both processed data and embeddings
            proc_files = list(PROCESSED_DATA_DIR.glob("processed_*.json"))
            embed_files = list(EMBEDDINGS_DIR.glob("embeddings_*.npz"))
            
            if proc_files and embed_files:
                processed_path = max(proc_files, key=lambda p: p.stat().st_mtime)
                embeddings_path = max(embed_files, key=lambda p: p.stat().st_mtime)
                await stage_5_vector_indexing(processed_path, embeddings_path)
            else:
                print("❌ Stage 5 requires both processed data and embeddings.")
                print("   Run stages 2 and 4 first.")
        elif args.stage == 6:
            if not input_path:
                proc_files = list(PROCESSED_DATA_DIR.glob("processed_*.json"))
                input_path = max(proc_files, key=lambda p: p.stat().st_mtime) if proc_files else None
            if input_path:
                await stage_6_selfrag_generation(input_path)
    else:
        # Run full pipeline
        await run_full_pipeline(
            extraction_limit=args.limit,
            dry_run=not args.execute,
            skip_stages=args.skip,
        )


if __name__ == "__main__":
    asyncio.run(main())
