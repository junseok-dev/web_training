"""
Short-Cut v3.0 - PAI-NET Triplet Generator
==============================================
Generates [Anchor - Positive - Negative] triplets for patent embedding training.

Uses citation relationships:
- Positive pairs: Patents that cite each other
- Negative pairs: Patents with no citation relationship

Author: Team 뀨💕
License: MIT
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict
from datetime import datetime

from tqdm import tqdm

from src.config import config, PAINETConfig, TRIPLETS_DIR

# =============================================================================
# Logging Setup
# =============================================================================

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TripletSample:
    """A single triplet for contrastive learning."""
    anchor_id: str
    anchor_text: str
    positive_id: str
    positive_text: str
    negative_id: str
    negative_text: str
    
    # Metadata
    citation_type: Optional[str] = None  # 'A', 'D', 'X', 'Y' etc.
    negative_sampling_method: str = "random"  # "random" or "hard"
    anchor_ipc: Optional[str] = None
    positive_ipc: Optional[str] = None
    negative_ipc: Optional[str] = None


@dataclass
class TripletDataset:
    """Collection of triplets with metadata."""
    triplets: List[TripletSample]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Statistics
    total_triplets: int = 0
    unique_anchors: int = 0
    unique_positives: int = 0
    unique_negatives: int = 0
    hard_negative_ratio: float = 0.0
    
    def __post_init__(self):
        self.total_triplets = len(self.triplets)
        self.unique_anchors = len(set(t.anchor_id for t in self.triplets))
        self.unique_positives = len(set(t.positive_id for t in self.triplets))
        self.unique_negatives = len(set(t.negative_id for t in self.triplets))
        
        if self.triplets:
            hard_count = sum(1 for t in self.triplets if t.negative_sampling_method == "hard")
            self.hard_negative_ratio = hard_count / len(self.triplets)


@dataclass
class PatentNode:
    """Node in the citation graph."""
    publication_number: str
    text: str  # Primary text for embedding (usually claims or abstract)
    ipc_code: Optional[str] = None
    cited_by: Set[str] = field(default_factory=set)  # Patents that cite this one
    cites: Set[str] = field(default_factory=set)  # Patents this one cites
    importance_score: float = 0.0


# =============================================================================
# Citation Graph Builder
# =============================================================================

class CitationGraph:
    """
    Build and manage citation relationships between patents.
    
    Used for:
    - Identifying positive pairs (citation relationships)
    - Generating hard negatives (same IPC, no citation)
    - Computing importance scores (citation count)
    """
    
    def __init__(self):
        self.nodes: Dict[str, PatentNode] = {}
        self.ipc_index: Dict[str, Set[str]] = defaultdict(set)  # IPC -> patent IDs
    
    def add_patent(
        self,
        publication_number: str,
        text: str,
        ipc_code: Optional[str] = None,
        cited_publications: Optional[List[str]] = None,
    ) -> None:
        """Add a patent to the graph."""
        node = PatentNode(
            publication_number=publication_number,
            text=text,
            ipc_code=ipc_code,
        )
        
        self.nodes[publication_number] = node
        
        # Add to IPC index
        if ipc_code:
            # Use first 4 characters of IPC code for grouping
            ipc_group = ipc_code[:4] if len(ipc_code) >= 4 else ipc_code
            self.ipc_index[ipc_group].add(publication_number)
        
        # Process citations
        if cited_publications:
            for cited_id in cited_publications:
                if cited_id:
                    node.cites.add(cited_id)
                    
                    # Update cited patent's "cited_by" set
                    if cited_id in self.nodes:
                        self.nodes[cited_id].cited_by.add(publication_number)
    
    def build_from_processed_patents(
        self,
        processed_patents: List[Dict[str, any]],
        text_field: str = "abstract",  # or "claims"
    ) -> None:
        """
        Build graph from processed patent data.
        
        Args:
            processed_patents: List of processed patent dictionaries
            text_field: Field to use for text ("abstract" or "claims")
        """
        logger.info(f"Building citation graph from {len(processed_patents)} patents...")
        
        for patent in tqdm(processed_patents, desc="Building graph"):
            pub_num = patent.get('publication_number', '')
            
            # Get text
            if text_field == "claims" and patent.get('claims'):
                # Combine all claims
                claims = patent['claims']
                text = " ".join([c.get('claim_text', '') for c in claims if isinstance(c, dict)])
            else:
                text = patent.get('abstract', '')
            
            # Get IPC code (first one)
            ipc_codes = patent.get('ipc_codes', [])
            ipc_code = ipc_codes[0] if ipc_codes else None
            
            # Get citations
            cited = patent.get('cited_publications', [])
            
            self.add_patent(
                publication_number=pub_num,
                text=text,
                ipc_code=ipc_code,
                cited_publications=cited,
            )
        
        # Update importance scores
        self._compute_importance_scores()
        
        # Second pass: complete bidirectional links
        self._complete_citation_links()
        
        logger.info(f"Graph built: {len(self.nodes)} nodes, {len(self.ipc_index)} IPC groups")
    
    def _compute_importance_scores(self) -> None:
        """Compute importance scores based on citation count."""
        for node in self.nodes.values():
            # Importance = number of patents citing this one
            node.importance_score = len(node.cited_by)
    
    def _complete_citation_links(self) -> None:
        """Ensure bidirectional citation links are complete."""
        for pub_num, node in self.nodes.items():
            for cited_id in node.cites:
                if cited_id in self.nodes:
                    self.nodes[cited_id].cited_by.add(pub_num)
    
    def get_positive_pairs(
        self,
        min_importance: float = 0,
    ) -> List[Tuple[str, str]]:
        """
        Get all positive pairs (citation relationships).
        
        Returns:
            List of (anchor_id, positive_id) tuples
        """
        pairs = []
        
        for pub_num, node in self.nodes.items():
            if node.importance_score < min_importance:
                continue
            
            # Add pairs for patents this one cites
            for cited_id in node.cites:
                if cited_id in self.nodes:
                    pairs.append((pub_num, cited_id))
        
        return pairs
    
    def get_hard_negatives(
        self,
        anchor_id: str,
        positive_id: str,
        n_samples: int = 1,
    ) -> List[str]:
        """
        Get hard negative samples.
        
        Hard negatives: Same IPC code but no citation relationship.
        
        Args:
            anchor_id: Anchor patent ID
            positive_id: Positive patent ID
            n_samples: Number of negatives to sample
            
        Returns:
            List of negative patent IDs
        """
        anchor_node = self.nodes.get(anchor_id)
        if not anchor_node or not anchor_node.ipc_code:
            return []
        
        ipc_group = anchor_node.ipc_code[:4] if len(anchor_node.ipc_code) >= 4 else anchor_node.ipc_code
        
        # Get patents with same IPC
        same_ipc_patents = self.ipc_index.get(ipc_group, set())
        
        # Exclude anchor, positive, and any cited/citing patents
        excluded = {anchor_id, positive_id}
        excluded.update(anchor_node.cites)
        excluded.update(anchor_node.cited_by)
        
        candidates = [p for p in same_ipc_patents if p not in excluded and p in self.nodes]
        
        if not candidates:
            return []
        
        return random.sample(candidates, min(n_samples, len(candidates)))
    
    def get_random_negatives(
        self,
        anchor_id: str,
        positive_id: str,
        n_samples: int = 1,
    ) -> List[str]:
        """
        Get random negative samples.
        
        Random negatives: Any patent with no citation relationship.
        
        Args:
            anchor_id: Anchor patent ID
            positive_id: Positive patent ID
            n_samples: Number of negatives to sample
            
        Returns:
            List of negative patent IDs
        """
        anchor_node = self.nodes.get(anchor_id)
        if not anchor_node:
            return []
        
        # Exclude anchor, positive, and any cited/citing patents
        excluded = {anchor_id, positive_id}
        excluded.update(anchor_node.cites)
        excluded.update(anchor_node.cited_by)
        
        candidates = [p for p in self.nodes.keys() if p not in excluded]
        
        if not candidates:
            return []
        
        return random.sample(candidates, min(n_samples, len(candidates)))


# =============================================================================
# Triplet Generator
# =============================================================================

class PAINETTripletGenerator:
    """
    Generate triplets for PAI-NET training.
    
    Creates [Anchor - Positive - Negative] samples where:
    - Anchor: A patent with citations
    - Positive: A patent cited by the anchor
    - Negative: A patent not cited (hard or random sampling)
    """
    
    def __init__(self, painet_config: PAINETConfig = config.painet):
        self.config = painet_config
        self.graph = CitationGraph()
    
    def build_graph(
        self,
        processed_patents: List[Dict[str, Any]],
        text_field: str = "abstract",
    ) -> None:
        """Build citation graph from processed patents."""
        self.graph.build_from_processed_patents(processed_patents, text_field)
    
    async def generate_triplets(
        self,
        output_path: Optional[Path] = None,
    ) -> TripletDataset:
        """
        Generate all triplets.
        
        Args:
            output_path: Optional path to save triplets
            
        Returns:
            TripletDataset containing all generated triplets
        """
        logger.info("Generating PAI-NET triplets...")
        
        triplets = []
        
        # Get positive pairs
        positive_pairs = self.graph.get_positive_pairs(
            min_importance=self.config.min_citations_for_anchor
        )
        
        logger.info(f"Found {len(positive_pairs)} positive pairs")
        
        # Generate triplets for each positive pair
        for anchor_id, positive_id in tqdm(positive_pairs, desc="Generating triplets"):
            anchor_node = self.graph.nodes.get(anchor_id)
            positive_node = self.graph.nodes.get(positive_id)
            
            if not anchor_node or not positive_node:
                continue
            
            if not anchor_node.text or not positive_node.text:
                continue
            
            # Calculate number of hard vs random negatives
            total_negs = self.config.negatives_per_positive
            n_hard = int(total_negs * self.config.hard_negative_ratio)
            n_random = total_negs - n_hard
            
            # Get hard negatives
            hard_negs = self.graph.get_hard_negatives(anchor_id, positive_id, n_hard)
            
            # Get random negatives
            random_negs = self.graph.get_random_negatives(anchor_id, positive_id, n_random)
            
            # Create triplets with hard negatives
            for neg_id in hard_negs:
                neg_node = self.graph.nodes.get(neg_id)
                if neg_node and neg_node.text:
                    triplets.append(TripletSample(
                        anchor_id=anchor_id,
                        anchor_text=anchor_node.text,
                        positive_id=positive_id,
                        positive_text=positive_node.text,
                        negative_id=neg_id,
                        negative_text=neg_node.text,
                        negative_sampling_method="hard",
                        anchor_ipc=anchor_node.ipc_code,
                        positive_ipc=positive_node.ipc_code,
                        negative_ipc=neg_node.ipc_code,
                    ))
            
            # Create triplets with random negatives
            for neg_id in random_negs:
                neg_node = self.graph.nodes.get(neg_id)
                if neg_node and neg_node.text:
                    triplets.append(TripletSample(
                        anchor_id=anchor_id,
                        anchor_text=anchor_node.text,
                        positive_id=positive_id,
                        positive_text=positive_node.text,
                        negative_id=neg_id,
                        negative_text=neg_node.text,
                        negative_sampling_method="random",
                        anchor_ipc=anchor_node.ipc_code,
                        positive_ipc=positive_node.ipc_code,
                        negative_ipc=neg_node.ipc_code,
                    ))
        
        # Create dataset
        dataset = TripletDataset(triplets=triplets)
        
        logger.info(f"Generated {dataset.total_triplets} triplets")
        logger.info(f"  Unique anchors: {dataset.unique_anchors}")
        logger.info(f"  Hard negative ratio: {dataset.hard_negative_ratio:.2%}")
        
        # Save if path provided
        if output_path:
            self._save_dataset(dataset, output_path)
        
        return dataset
    
    def _save_dataset(self, dataset: TripletDataset, output_path: Path) -> None:
        """Save dataset to file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if self.config.output_format == "jsonl":
            # Save as JSON Lines for streaming
            with open(output_path, 'w', encoding='utf-8') as f:
                for triplet in dataset.triplets:
                    f.write(json.dumps(asdict(triplet), ensure_ascii=False) + '\n')
        else:
            # Save as single JSON
            data = {
                "metadata": {
                    "created_at": dataset.created_at,
                    "total_triplets": dataset.total_triplets,
                    "unique_anchors": dataset.unique_anchors,
                    "unique_positives": dataset.unique_positives,
                    "unique_negatives": dataset.unique_negatives,
                    "hard_negative_ratio": dataset.hard_negative_ratio,
                },
                "triplets": [asdict(t) for t in dataset.triplets],
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved triplets to: {output_path}")


# =============================================================================
# CLI Entry Point
# =============================================================================

async def main():
    """Main entry point for standalone execution."""
    import sys
    from src.config import PROCESSED_DATA_DIR
    
    logging.basicConfig(
        level=logging.INFO,
        format=config.logging.log_format,
    )
    
    print("\n" + "=" * 70)
    print("⚡ 쇼특허 (Short-Cut) v3.0 - PAI-NET Triplet Generator")
    print("=" * 70)
    
    # Check for input file
    if len(sys.argv) < 2:
        # Look for most recent processed data
        processed_files = list(PROCESSED_DATA_DIR.glob("processed_*.json"))
        if not processed_files:
            print("❌ No processed patent data found. Run preprocessor.py first.")
            return
        input_path = max(processed_files, key=lambda p: p.stat().st_mtime)
    else:
        input_path = Path(sys.argv[1])
    
    print(f"📂 Input: {input_path}")
    
    # Load processed data
    with open(input_path, 'r', encoding='utf-8') as f:
        processed_patents = json.load(f)
    
    print(f"📊 Loaded {len(processed_patents)} processed patents")
    
    # Generate triplets
    generator = PAINETTripletGenerator()
    generator.build_graph(processed_patents, text_field="abstract")
    
    output_path = TRIPLETS_DIR / f"triplets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    dataset = await generator.generate_triplets(output_path)
    
    print(f"\n✅ Triplet generation complete!")
    print(f"   Total: {dataset.total_triplets}")
    print(f"   Anchors: {dataset.unique_anchors}")
    print(f"   Hard Neg Ratio: {dataset.hard_negative_ratio:.2%}")
    print(f"   Output: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
