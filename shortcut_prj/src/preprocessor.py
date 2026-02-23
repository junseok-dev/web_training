"""
Short-Cut v3.0 - Patent Data Preprocessor
=============================================
Processes raw patent data with hierarchical chunking and claim parsing.

Features:
- Individual claim extraction (Claim 1, 2, 3...)
- Parent-Child chunking strategy
- RAG component keyword tagging
- Async batch processing

Author: Team 뀨💕
License: MIT
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from tqdm import tqdm

from src.config import config, DomainConfig, PROCESSED_DATA_DIR

# =============================================================================
# Logging Setup
# =============================================================================

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ParsedClaim:
    """Represents a single parsed claim."""
    claim_number: int
    claim_text: str
    claim_type: str  # "independent" or "dependent"
    parent_claim: Optional[int]  # Reference to parent claim if dependent
    rag_components: List[str]  # Detected RAG component keywords
    char_count: int = 0
    word_count: int = 0
    
    def __post_init__(self):
        self.char_count = len(self.claim_text)
        self.word_count = len(self.claim_text.split())


@dataclass
class PatentChunk:
    """Represents a chunk of patent content."""
    chunk_id: str
    patent_id: str
    chunk_type: str  # "parent", "claim", "abstract", "description_section"
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    rag_components: List[str] = field(default_factory=list)
    
    # Hierarchy
    parent_chunk_id: Optional[str] = None
    child_chunk_ids: List[str] = field(default_factory=list)


@dataclass
class ProcessedPatent:
    """Fully processed patent document."""
    publication_number: str
    title: str
    abstract: str
    filing_date: Optional[str]
    
    # Parsed claims
    claims: List[ParsedClaim]
    
    # Chunked content
    chunks: List[PatentChunk]
    
    # Classification
    ipc_codes: List[str]
    cpc_codes: List[str]
    
    # Citations
    cited_publications: List[str]
    citation_count: int
    
    # RAG relevance
    rag_component_tags: List[str]
    importance_score: float
    
    # Metadata
    processed_at: str = field(default_factory=lambda: datetime.now().isoformat())


# =============================================================================
# Claim Parser (Enhanced v3.0)
# =============================================================================

class ClaimParser:
    """
    Enhanced patent claim parser with multi-level fallback.
    
    Parsing Strategy (in order):
    1. Regex Pattern Matching - Standard claim formats
    2. Structure-Based Parsing - Indent and numbering analysis
    3. NLP Sentence Segmentation - Spacy-based fallback
    4. Minimal Split - Ultimate fallback for any text
    
    Supports:
    - US/EP format: "1. A method comprising..."
    - Korean format: "제1항: ...", "청구항 1: ..."
    - Mixed numbering: "(1)", "[1]", "1)", etc.
    """
    
    # Regex patterns for claim extraction (ordered by format commonality)
    CLAIM_PATTERNS = [
        # Pattern 1: Standard US/EP "1. A method comprising..." - MOST COMMON
        r'(?P<num>\d+)\.\s*(?P<text>(?:(?!\n\d+\.).)+)',
        
        # Pattern 2: "Claim 1: A method..."
        r'[Cc]laim\s*(?P<num>\d+)[:\.]?\s*(?P<text>(?:(?!\n[Cc]laim\s*\d+).)+)',
        
        # Pattern 3: Numbered with parentheses "(1) A method..."
        r'\((?P<num>\d+)\)\s*(?P<text>(?:(?!\n\(\d+\)).)+)',
        
        # Pattern 4: Numbered with brackets "[1] A method..."
        r'\[(?P<num>\d+)\]\s*(?P<text>(?:(?!\n\[\d+\]).)+)',
        
        # Pattern 5: Korean format "제1항:" or "청구항 1:"
        r'(?:제|청구항\s*)(?P<num>\d+)(?:항)?[:\.]?\s*(?P<text>(?:(?!\n(?:제|청구항\s*)\d+).)+)',
        
        # Pattern 6: Simple numbered "1)" format
        r'(?P<num>\d+)\)\s*(?P<text>(?:(?!\n\d+\)).)+)',
    ]
    
    # Patterns indicating dependent claims (multilingual)
    DEPENDENT_PATTERNS = [
        # English patterns
        r'according to claim\s*(\d+)',
        r'as claimed in claim\s*(\d+)',
        r'of claim\s*(\d+)',
        r'claim\s*(\d+),?\s*wherein',
        r'the (?:method|system|apparatus|device|invention) of claim\s*(\d+)',
        r'as set forth in claim\s*(\d+)',
        
        # Korean patterns
        r'제\s*(\d+)\s*항에\s*있어서',
        r'청구항\s*(\d+)에\s*있어서',
        r'제\s*(\d+)\s*항에\s*따른',
    ]
    
    # NLP model cache
    _nlp = None
    _nlp_available = None
    
    def __init__(self, domain_config: DomainConfig = config.domain):
        self.rag_keywords = [kw.lower() for kw in domain_config.rag_component_keywords]
        self._init_nlp()
    
    @classmethod
    def _init_nlp(cls):
        """Initialize Spacy NLP model for fallback parsing."""
        if cls._nlp_available is not None:
            return
        
        try:
            import spacy
            try:
                cls._nlp = spacy.load("en_core_web_sm")
                cls._nlp_available = True
                logger.info("Spacy NLP model loaded for claim parsing")
            except OSError:
                # Model not installed
                cls._nlp_available = False
                logger.warning("Spacy model 'en_core_web_sm' not found. Install with: python -m spacy download en_core_web_sm")
        except ImportError:
            cls._nlp_available = False
            logger.warning("Spacy not installed. NLP fallback disabled. Install with: pip install spacy")
    
    def parse_claims_text(self, claims_text: str) -> List[ParsedClaim]:
        """
        Parse claims text into individual claims using multi-level fallback.
        
        Args:
            claims_text: Full claims section text
            
        Returns:
            List of ParsedClaim objects
        """
        if not claims_text or not claims_text.strip():
            return []
        
        # Clean input
        claims_text = self._preprocess_text(claims_text)
        
        # Level 1: Regex Pattern Matching
        claims = self._regex_parse(claims_text)
        if claims:
            logger.debug(f"Parsed {len(claims)} claims using regex patterns")
            return self._finalize_claims(claims)
        
        # Level 2: Structure-Based Parsing (indent/numbering)
        claims = self._structure_based_parse(claims_text)
        if claims:
            logger.debug(f"Parsed {len(claims)} claims using structure analysis")
            return self._finalize_claims(claims)
        
        # Level 3: NLP Sentence Segmentation
        if self._nlp_available and self._nlp:
            claims = self._nlp_fallback_parse(claims_text)
            if claims:
                logger.debug(f"Parsed {len(claims)} claims using NLP segmentation")
                return self._finalize_claims(claims)
        
        # Level 4: Minimal Split (ultimate fallback)
        claims = self._minimal_parse(claims_text)
        logger.debug(f"Parsed {len(claims)} claims using minimal split")
        return self._finalize_claims(claims)
    
    def _preprocess_text(self, text: str) -> str:
        """Preprocess claims text for parsing."""
        # Normalize line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Remove common header patterns
        text = re.sub(r'^(?:CLAIMS?|What is claimed is:?|We claim:?)\s*\n', '', text, flags=re.IGNORECASE)
        
        # Normalize multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()
    
    def _regex_parse(self, claims_text: str) -> List[ParsedClaim]:
        """Level 1: Standard regex pattern matching."""
        claims = []
        
        for pattern in self.CLAIM_PATTERNS:
            matches = list(re.finditer(pattern, claims_text, re.DOTALL | re.MULTILINE))
            if matches and len(matches) >= 1:
                for match in matches:
                    claim_num = int(match.group('num'))
                    claim_text = self._clean_claim_text(match.group('text'))
                    
                    if claim_text and len(claim_text) > 10:  # Skip very short claims
                        claim_type, parent_claim = self._determine_claim_type(claim_text)
                        rag_components = self._detect_rag_components(claim_text)
                        
                        claims.append(ParsedClaim(
                            claim_number=claim_num,
                            claim_text=claim_text,
                            claim_type=claim_type,
                            parent_claim=parent_claim,
                            rag_components=rag_components,
                        ))
                
                if claims:  # Only return if we found valid claims
                    break
        
        return claims
    
    def _structure_based_parse(self, claims_text: str) -> List[ParsedClaim]:
        """
        Level 2: Parse based on document structure (indent, numbering).
        
        Analyzes:
        - Indentation levels
        - Numbering patterns
        - Line breaks between claims
        """
        claims = []
        lines = claims_text.split('\n')
        
        # Detect numbering patterns in the document
        numbered_lines = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Various numbering patterns
            patterns = [
                (r'^(\d+)[.\):\]]\s*(.*)$', 1, 2),  # "1. ", "1) ", "1: ", "1] "
                (r'^\[(\d+)\]\s*(.*)$', 1, 2),       # "[1] "
                (r'^\((\d+)\)\s*(.*)$', 1, 2),       # "(1) "
                (r'^(?:Claim|제|청구항)\s*(\d+)[:\.]?\s*(.*)$', 1, 2),  # "Claim 1: "
            ]
            
            for pattern, num_group, text_group in patterns:
                match = re.match(pattern, stripped, re.IGNORECASE)
                if match:
                    indent = len(line) - len(line.lstrip())
                    numbered_lines.append({
                        'line_idx': i,
                        'num': int(match.group(num_group)),
                        'text_start': match.group(text_group),
                        'indent': indent,
                    })
                    break
        
        if not numbered_lines:
            return []
        
        # Build claims from numbered sections
        for idx, item in enumerate(numbered_lines):
            start_line = item['line_idx']
            
            # Find end of this claim (next numbered line or end)
            if idx + 1 < len(numbered_lines):
                end_line = numbered_lines[idx + 1]['line_idx']
            else:
                end_line = len(lines)
            
            # Collect claim text
            claim_lines = [item['text_start']]
            for j in range(start_line + 1, end_line):
                line_text = lines[j].strip()
                if line_text:
                    claim_lines.append(line_text)
            
            claim_text = ' '.join(claim_lines)
            claim_text = self._clean_claim_text(claim_text)
            
            if claim_text and len(claim_text) > 10:
                claim_type, parent = self._determine_claim_type(claim_text)
                claims.append(ParsedClaim(
                    claim_number=item['num'],
                    claim_text=claim_text,
                    claim_type=claim_type,
                    parent_claim=parent,
                    rag_components=self._detect_rag_components(claim_text),
                ))
        
        return claims
    
    def _nlp_fallback_parse(self, claims_text: str) -> List[ParsedClaim]:
        """
        Level 3: NLP-based sentence segmentation fallback.
        
        Uses Spacy for sentence boundary detection when structured
        parsing fails.
        """
        if not self._nlp:
            return []
        
        claims = []
        
        # Process with Spacy
        doc = self._nlp(claims_text[:100000])  # Limit for performance
        
        sentences = list(doc.sents)
        if not sentences:
            return []
        
        claim_num = 0
        current_claim_sentences = []
        
        for sent in sentences:
            sent_text = sent.text.strip()
            
            # Check if sentence starts a new numbered claim
            num_match = re.match(r'^(\d+)[.\):\]]\s*', sent_text)
            
            if num_match:
                # Save previous claim
                if current_claim_sentences:
                    claim_text = ' '.join(current_claim_sentences)
                    claim_text = self._clean_claim_text(claim_text)
                    if claim_text and len(claim_text) > 10:
                        claim_type, parent = self._determine_claim_type(claim_text)
                        claims.append(ParsedClaim(
                            claim_number=claim_num if claim_num > 0 else 1,
                            claim_text=claim_text,
                            claim_type=claim_type,
                            parent_claim=parent,
                            rag_components=self._detect_rag_components(claim_text),
                        ))
                
                claim_num = int(num_match.group(1))
                current_claim_sentences = [sent_text[num_match.end():].strip()]
            else:
                current_claim_sentences.append(sent_text)
        
        # Don't forget last claim
        if current_claim_sentences:
            claim_text = ' '.join(current_claim_sentences)
            claim_text = self._clean_claim_text(claim_text)
            if claim_text and len(claim_text) > 10:
                claim_type, parent = self._determine_claim_type(claim_text)
                claims.append(ParsedClaim(
                    claim_number=claim_num if claim_num > 0 else len(claims) + 1,
                    claim_text=claim_text,
                    claim_type=claim_type,
                    parent_claim=parent,
                    rag_components=self._detect_rag_components(claim_text),
                ))
        
        return claims
    
    def _minimal_parse(self, claims_text: str) -> List[ParsedClaim]:
        """
        Level 4: Ultimate fallback - split by paragraph or treat as single claim.
        """
        claims = []
        
        # Try splitting by double newlines (paragraphs) or single newlines with blank lines
        # Also handle Windows-style line endings
        paragraphs = re.split(r'\n\s*\n|\r\n\s*\r\n', claims_text)
        paragraphs = [p.strip() for p in paragraphs if p.strip() and len(p.strip()) > 15]
        
        if len(paragraphs) > 1:
            # Multiple paragraphs - treat each as a claim
            for i, para in enumerate(paragraphs, 1):
                claim_text = self._clean_claim_text(para)
                if claim_text:
                    claim_type, parent = self._determine_claim_type(claim_text)
                    claims.append(ParsedClaim(
                        claim_number=i,
                        claim_text=claim_text,
                        claim_type=claim_type,
                        parent_claim=parent,
                        rag_components=self._detect_rag_components(claim_text),
                    ))
        else:
            # Single block - treat as claim 1
            claim_text = self._clean_claim_text(claims_text)
            if claim_text:
                claims.append(ParsedClaim(
                    claim_number=1,
                    claim_text=claim_text,
                    claim_type="independent",
                    parent_claim=None,
                    rag_components=self._detect_rag_components(claim_text),
                ))
        
        return claims
    
    def _finalize_claims(self, claims: List[ParsedClaim]) -> List[ParsedClaim]:
        """Sort and deduplicate claims."""
        # Remove duplicates by claim number (keep first)
        seen_nums = set()
        unique_claims = []
        for claim in claims:
            if claim.claim_number not in seen_nums:
                seen_nums.add(claim.claim_number)
                unique_claims.append(claim)
        
        # Sort by claim number
        unique_claims.sort(key=lambda c: c.claim_number)
        
        return unique_claims
    
    def _clean_claim_text(self, text: str) -> str:
        """Clean and normalize claim text."""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Strip leading/trailing whitespace
        text = text.strip()
        
        # Remove trailing claim numbers from next claim
        text = re.sub(r'\s*\d+\.\s*$', '', text)
        
        # Remove common artifacts
        text = re.sub(r'^[-*•]\s*', '', text)  # Bullet points
        
        return text
    
    def _determine_claim_type(self, claim_text: str) -> Tuple[str, Optional[int]]:
        """
        Determine if claim is independent or dependent.
        
        Returns:
            Tuple of (claim_type, parent_claim_number)
        """
        claim_lower = claim_text.lower()
        
        for pattern in self.DEPENDENT_PATTERNS:
            match = re.search(pattern, claim_lower)
            if match:
                parent_num = int(match.group(1))
                return "dependent", parent_num
        
        return "independent", None
    
    def _detect_rag_components(self, claim_text: str) -> List[str]:
        """Detect RAG-related component keywords in claim."""
        if not claim_text:
            return []
        
        claim_lower = claim_text.lower()
        detected = []
        
        for keyword in self.rag_keywords:
            if keyword in claim_lower:
                detected.append(keyword)
        
        return detected


# =============================================================================
# Hierarchical Chunker
# =============================================================================

class HierarchicalChunker:
    """
    Create hierarchical chunks with Parent-Child strategy.
    
    Parent chunks: Full patent context
    Child chunks: Individual claims, description sections
    """
    
    def __init__(
        self,
        max_chunk_size: int = 8000,  # Characters
        overlap_size: int = 200,
        domain_config: DomainConfig = config.domain,
    ):
        self.max_chunk_size = max_chunk_size
        self.overlap_size = overlap_size
        self.rag_keywords = [kw.lower() for kw in domain_config.rag_component_keywords]
    
    def create_chunks(
        self,
        patent_id: str,
        title: str,
        abstract: str,
        claims: List[ParsedClaim],
        description: str = "",
    ) -> List[PatentChunk]:
        """
        Create hierarchical chunks for a patent.
        
        Args:
            patent_id: Publication number
            title: Patent title
            abstract: Patent abstract
            claims: Parsed claims
            description: Full description text
            
        Returns:
            List of PatentChunk objects
        """
        chunks = []
        
        # 1. Parent chunk (full context summary)
        parent_chunk = self._create_parent_chunk(
            patent_id, title, abstract, claims
        )
        chunks.append(parent_chunk)
        
        # 2. Abstract chunk
        if abstract:
            abstract_chunk = PatentChunk(
                chunk_id=f"{patent_id}_abstract",
                patent_id=patent_id,
                chunk_type="abstract",
                content=abstract,
                parent_chunk_id=parent_chunk.chunk_id,
                rag_components=self._detect_rag_components(abstract),
                metadata={"section": "abstract"},
            )
            chunks.append(abstract_chunk)
            parent_chunk.child_chunk_ids.append(abstract_chunk.chunk_id)
        
        # 3. Individual claim chunks
        for claim in claims:
            claim_chunk = PatentChunk(
                chunk_id=f"{patent_id}_claim_{claim.claim_number}",
                patent_id=patent_id,
                chunk_type="claim",
                content=claim.claim_text,
                parent_chunk_id=parent_chunk.chunk_id,
                rag_components=claim.rag_components,
                metadata={
                    "claim_number": claim.claim_number,
                    "claim_type": claim.claim_type,
                    "parent_claim": claim.parent_claim,
                },
            )
            chunks.append(claim_chunk)
            parent_chunk.child_chunk_ids.append(claim_chunk.chunk_id)
        
        # 4. Description section chunks (if provided)
        if description:
            desc_chunks = self._chunk_description(
                patent_id, description, parent_chunk.chunk_id
            )
            chunks.extend(desc_chunks)
            parent_chunk.child_chunk_ids.extend([c.chunk_id for c in desc_chunks])
        
        return chunks
    
    def _create_parent_chunk(
        self,
        patent_id: str,
        title: str,
        abstract: str,
        claims: List[ParsedClaim],
    ) -> PatentChunk:
        """Create parent chunk with full patent context."""
        
        # Combine key information
        content_parts = [
            f"Title: {title}",
            f"\nAbstract: {abstract}",
            f"\nNumber of Claims: {len(claims)}",
        ]
        
        # Add independent claims summary
        independent_claims = [c for c in claims if c.claim_type == "independent"]
        if independent_claims:
            content_parts.append("\nIndependent Claims Summary:")
            for claim in independent_claims[:3]:  # Top 3 independent claims
                content_parts.append(f"  Claim {claim.claim_number}: {claim.claim_text[:500]}...")
        
        content = "\n".join(content_parts)
        
        # Aggregate RAG components
        all_rag_components = set()
        for claim in claims:
            all_rag_components.update(claim.rag_components)
        all_rag_components.update(self._detect_rag_components(title))
        all_rag_components.update(self._detect_rag_components(abstract))
        
        return PatentChunk(
            chunk_id=f"{patent_id}_parent",
            patent_id=patent_id,
            chunk_type="parent",
            content=content,
            rag_components=list(all_rag_components),
            metadata={
                "title": title,
                "total_claims": len(claims),
                "independent_claims": len(independent_claims),
            },
        )
    
    def _chunk_description(
        self,
        patent_id: str,
        description: str,
        parent_chunk_id: str,
    ) -> List[PatentChunk]:
        """Chunk description into sections."""
        chunks = []
        
        # Split by common section headers
        section_pattern = r'(?:DETAILED DESCRIPTION|BACKGROUND|SUMMARY|BRIEF DESCRIPTION|CLAIMS|FIELD OF THE INVENTION)'
        
        sections = re.split(f'({section_pattern})', description, flags=re.IGNORECASE)
        
        section_name = "introduction"
        chunk_idx = 0
        
        for i, section in enumerate(sections):
            if not section.strip():
                continue
            
            # Check if this is a section header
            if re.match(section_pattern, section, re.IGNORECASE):
                section_name = section.strip().lower().replace(' ', '_')
                continue
            
            # Split large sections
            section_chunks = self._split_text(section)
            
            for j, chunk_text in enumerate(section_chunks):
                if not chunk_text.strip():
                    continue
                
                chunk = PatentChunk(
                    chunk_id=f"{patent_id}_desc_{chunk_idx}",
                    patent_id=patent_id,
                    chunk_type="description_section",
                    content=chunk_text,
                    parent_chunk_id=parent_chunk_id,
                    rag_components=self._detect_rag_components(chunk_text),
                    metadata={
                        "section": section_name,
                        "chunk_index": chunk_idx,
                    },
                )
                chunks.append(chunk)
                chunk_idx += 1
        
        return chunks
    
    def _split_text(self, text: str) -> List[str]:
        """Split text into chunks respecting max size with overlap."""
        if len(text) <= self.max_chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.max_chunk_size
            
            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence ending
                for sep in ['. ', '.\n', '! ', '? ']:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep > start + self.max_chunk_size // 2:
                        end = last_sep + 1
                        break
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            start = end - self.overlap_size
        
        return chunks
    
    def _detect_rag_components(self, text: str) -> List[str]:
        """Detect RAG component keywords in text."""
        if not text:
            return []
        
        text_lower = text.lower()
        detected = []
        
        for keyword in self.rag_keywords:
            if keyword in text_lower:
                detected.append(keyword)
        
        return detected


# =============================================================================
# Main Preprocessor
# =============================================================================

class PatentPreprocessor:
    """
    Main preprocessing pipeline for patent data.
    
    Combines claim parsing and hierarchical chunking.
    """
    
    def __init__(
        self,
        domain_config: DomainConfig = config.domain,
        max_chunk_size: int = 8000,
    ):
        self.claim_parser = ClaimParser(domain_config)
        self.chunker = HierarchicalChunker(max_chunk_size, domain_config=domain_config)
        self.domain_config = domain_config
    
    def process_patent(self, raw_patent: Dict[str, Any]) -> ProcessedPatent:
        """
        Process a single raw patent record.
        
        Args:
            raw_patent: Raw patent data from BigQuery
            
        Returns:
            ProcessedPatent object
        """
        publication_number = raw_patent.get('publication_number', 'UNKNOWN')
        
        # Extract text content
        title = self._extract_localized_text(raw_patent.get('title_localized', []))
        abstract = self._extract_localized_text(raw_patent.get('abstract_localized', []))
        claims_text = self._extract_localized_text(raw_patent.get('claims_localized', []))
        description = self._extract_localized_text(raw_patent.get('description_localized', []))
        
        # Parse claims
        parsed_claims = self.claim_parser.parse_claims_text(claims_text)
        
        # Create chunks
        chunks = self.chunker.create_chunks(
            patent_id=publication_number,
            title=title,
            abstract=abstract,
            claims=parsed_claims,
            description=description,
        )
        
        # Extract classification codes
        ipc_codes = self._extract_codes(raw_patent.get('ipc', []))
        cpc_codes = self._extract_codes(raw_patent.get('cpc', []))
        
        # Extract citations
        cited_publications = raw_patent.get('cited_publications', [])
        if not cited_publications:
            # Fallback: extract from citation array
            citations = raw_patent.get('citation', [])
            if citations:
                cited_publications = [
                    c.get('publication_number') or c.get('npl_text', '')
                    for c in citations
                    if c
                ]
        
        # Aggregate RAG components
        all_rag_components = set()
        for claim in parsed_claims:
            all_rag_components.update(claim.rag_components)
        for chunk in chunks:
            all_rag_components.update(chunk.rag_components)
        
        return ProcessedPatent(
            publication_number=publication_number,
            title=title,
            abstract=abstract,
            filing_date=raw_patent.get('filing_date_parsed'),
            claims=parsed_claims,
            chunks=chunks,
            ipc_codes=ipc_codes,
            cpc_codes=cpc_codes,
            cited_publications=cited_publications,
            citation_count=raw_patent.get('citation_count', len(cited_publications)),
            rag_component_tags=list(all_rag_components),
            importance_score=raw_patent.get('importance_score', 0.0),
        )
    
    async def process_patents_batch(
        self,
        raw_patents: List[Dict[str, Any]],
        output_path: Optional[Path] = None,
    ) -> List[ProcessedPatent]:
        """
        Process a batch of patents asynchronously.
        
        Args:
            raw_patents: List of raw patent records
            output_path: Optional path to save processed data
            
        Returns:
            List of ProcessedPatent objects
        """
        loop = asyncio.get_event_loop()
        
        processed = []
        
        for raw in tqdm(raw_patents, desc="Processing patents"):
            patent = await loop.run_in_executor(
                None, self.process_patent, raw
            )
            processed.append(patent)
        
        # Save if path provided
        if output_path:
            self._save_processed_patents(processed, output_path)
        
        return processed
    
    def _extract_localized_text(
        self,
        localized_texts: List[Dict[str, str]],
        preferred_lang: str = "en",
    ) -> str:
        """Extract text from localized array, preferring English."""
        if not localized_texts:
            return ""
        
        # Try preferred language first
        for item in localized_texts:
            if isinstance(item, dict) and item.get('language') == preferred_lang:
                return item.get('text', '')
        
        # Fallback to first available
        if isinstance(localized_texts[0], dict):
            return localized_texts[0].get('text', '')
        elif isinstance(localized_texts[0], str):
            return localized_texts[0]
        
        return ""
    
    def _extract_codes(self, code_array: List[Any]) -> List[str]:
        """Extract classification codes from array."""
        codes = []
        
        for item in code_array:
            if isinstance(item, dict):
                code = item.get('code', '')
                if code:
                    codes.append(code)
            elif isinstance(item, str):
                codes.append(item)
        
        return codes
    
    def _save_processed_patents(
        self,
        patents: List[ProcessedPatent],
        output_path: Path,
    ) -> None:
        """Save processed patents to JSON file."""
        from dataclasses import asdict
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to serializable format
        data = []
        for patent in patents:
            patent_dict = asdict(patent)
            # Convert ParsedClaim and PatentChunk to dicts
            patent_dict['claims'] = [asdict(c) for c in patent.claims]
            patent_dict['chunks'] = [asdict(c) for c in patent.chunks]
            data.append(patent_dict)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(patents)} processed patents to: {output_path}")


# =============================================================================
# CLI Entry Point
# =============================================================================

async def main():
    """Main entry point for standalone execution."""
    import sys
    from config import RAW_DATA_DIR
    
    logging.basicConfig(
        level=logging.INFO,
        format=config.logging.log_format,
    )
    
    print("\n" + "=" * 70)
    print("⚡ 쇼특허 (Short-Cut) v3.0 - Patent Preprocessor")
    print("=" * 70)
    
    # Check for input file argument
    if len(sys.argv) < 2:
        # Look for most recent raw data file
        raw_files = list(RAW_DATA_DIR.glob("patents_*.json"))
        if not raw_files:
            print("❌ No raw patent data found. Run bigquery_extractor.py first.")
            return
        input_path = max(raw_files, key=lambda p: p.stat().st_mtime)
    else:
        input_path = Path(sys.argv[1])
    
    print(f"📂 Input: {input_path}")
    
    # Load raw data
    with open(input_path, 'r', encoding='utf-8') as f:
        raw_patents = json.load(f)
    
    print(f"📊 Loaded {len(raw_patents)} raw patents")
    
    # Process
    preprocessor = PatentPreprocessor()
    
    output_path = PROCESSED_DATA_DIR / f"processed_{input_path.stem}.json"
    processed = await preprocessor.process_patents_batch(raw_patents, output_path)
    
    # Summary
    total_claims = sum(len(p.claims) for p in processed)
    total_chunks = sum(len(p.chunks) for p in processed)
    rag_tagged = sum(1 for p in processed if p.rag_component_tags)
    
    print(f"\n✅ Processing complete!")
    print(f"   Patents: {len(processed)}")
    print(f"   Claims: {total_claims}")
    print(f"   Chunks: {total_chunks}")
    print(f"   RAG-tagged: {rag_tagged}")
    print(f"   Output: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
