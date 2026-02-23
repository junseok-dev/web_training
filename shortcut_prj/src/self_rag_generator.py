"""
Short-Cut v3.0 - Self-RAG Training Data Generator
=====================================================
Generate training data for Self-RAG with critical patent analysis.

Uses OpenAI GPT to:
- Compare anchor and cited patent claims
- Generate [유사도 평가], [침해 리스크], [회피 전략] analysis
- Create ground truth for Self-RAG training

Author: Team 뀨💕
License: MIT
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import re

from tqdm import tqdm

from src.config import config, SelfRAGConfig, PROCESSED_DATA_DIR


# =============================================================================
# Logging Setup
# =============================================================================

logger = logging.getLogger(__name__)


# =============================================================================
# Lazy Import OpenAI
# =============================================================================

try:
    from openai import OpenAI, AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("openai 설치 필요: pip install openai")


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SimilarityAssessment:
    """유사도 평가 section."""
    score: int  # 0-100
    common_elements: List[str]
    summary: str


@dataclass
class InfringementRisk:
    """침해 리스크 section."""
    risk_level: str  # "high", "medium", "low"
    risk_factors: List[str]
    summary: str


@dataclass
class DesignAroundStrategy:
    """회피 전략 section."""
    strategies: List[str]
    alternative_approaches: List[str]
    summary: str


@dataclass
class CritiqueResult:
    """Full critique result from OpenAI."""
    anchor_id: str
    cited_id: str
    anchor_claim: str
    cited_claim: str
    
    similarity: SimilarityAssessment
    infringement: InfringementRisk
    design_around: DesignAroundStrategy
    
    raw_response: str
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    model_used: str = ""


@dataclass
class SelfRAGTrainingSample:
    """Training sample for Self-RAG."""
    sample_id: str
    
    # Input context
    query: str  # Question about similarity/infringement
    anchor_patent_id: str
    anchor_claim: str
    cited_patent_id: str
    cited_claim: str
    
    # Ground truth output
    ground_truth_critique: str
    
    # Structured analysis
    similarity_score: int
    risk_level: str
    
    # Metadata
    rag_components_anchor: List[str] = field(default_factory=list)
    rag_components_cited: List[str] = field(default_factory=list)
    
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


# =============================================================================
# OpenAI Critique Generator
# =============================================================================

class OpenAICritiqueGenerator:
    """
    Generate patent critiques using OpenAI GPT.
    
    Produces structured analysis with:
    - 유사도 평가 (Similarity Assessment)
    - 침해 리스크 (Infringement Risk)
    - 회피 전략 (Design-Around Strategy)
    """
    
    def __init__(self, self_rag_config: SelfRAGConfig = config.self_rag):
        self.config = self_rag_config
        self.client = None
        self.async_client = None
        
        if not OPENAI_AVAILABLE:
            raise ImportError("openai required. Install with: pip install openai")
        
        if not self.config.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set. Set via environment variable or .env file.")
    
    def _init_client(self) -> None:
        """Initialize OpenAI clients."""
        if self.client is not None:
            return
        
        self.client = OpenAI(api_key=self.config.openai_api_key)
        self.async_client = AsyncOpenAI(api_key=self.config.openai_api_key)
        
        logger.info(f"Initialized OpenAI client with model: {self.config.openai_model}")
    
    async def generate_critique(
        self,
        anchor_id: str,
        anchor_claim: str,
        cited_id: str,
        cited_claim: str,
    ) -> CritiqueResult:
        """
        Generate critical analysis comparing two patent claims.
        
        Args:
            anchor_id: Anchor patent publication number
            anchor_claim: Anchor patent claim text
            cited_id: Cited patent publication number
            cited_claim: Cited patent claim text
            
        Returns:
            CritiqueResult with structured analysis
        """
        self._init_client()
        
        # Format prompt
        prompt = self.config.critique_prompt_template.format(
            anchor_publication_number=anchor_id,
            anchor_claim=anchor_claim[:8000],  # Truncate if too long
            cited_publication_number=cited_id,
            cited_claim=cited_claim[:8000],
        )
        
        # Append JSON formatting instruction
        prompt += """
        
반드시 아래 JSON 포맷을 정확히 준수하여 응답해 주십시오:
{
  "유사도 평가": {
    "기술적 유사성 점수": "0-100점",
    "핵심 공통 기술 요소": ["요소1", "요소2", "요소3"]
  },
  "침해 리스크": {
    "리스크 수준": "High/Medium/Low",
    "위험 요소": "구체적인 위험 요소 설명"
  },
  "회피 전략": {
    "분석 대상 특허가 선행 기술을 회피하기 위해 수정해야 할 구체적인 설계 변경 제안": ["제안1", "제안2"],
    "구성요소의 삭제, 치환, 변경을 포함한 실질적 조언": ["조언1", "조언2"]
  }
}
"""
        
        try:
            response = await self.async_client.chat.completions.create(
                model=self.config.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": "당신은 20년 경력의 특허 분쟁 대응 전문 변리사입니다. 단순히 정보를 나열하지 말고, 구성요소 대비 원칙(All Elements Rule)에 입각하여 침해 리스크를 '매우 비판적이고 보수적인' 관점에서 냉철하게 분석하십시오."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,  # Lower for more consistent analysis
                max_tokens=4096,
            )
            
            raw_response = response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            # Return empty result on error
            return CritiqueResult(
                anchor_id=anchor_id,
                cited_id=cited_id,
                anchor_claim=anchor_claim,
                cited_claim=cited_claim,
                similarity=SimilarityAssessment(0, [], f"Error: {e}"),
                infringement=InfringementRisk("unknown", [], f"Error: {e}"),
                design_around=DesignAroundStrategy([], [], f"Error: {e}"),
                raw_response=str(e),
                model_used=self.config.openai_model,
            )
        
        # Parse response
        similarity, infringement, design_around = self._parse_response(raw_response)
        
        return CritiqueResult(
            anchor_id=anchor_id,
            cited_id=cited_id,
            anchor_claim=anchor_claim,
            cited_claim=cited_claim,
            similarity=similarity,
            infringement=infringement,
            design_around=design_around,
            raw_response=raw_response,
            model_used=self.config.openai_model,
        )
    
    def _parse_response(
        self,
        response: str,
    ) -> Tuple[SimilarityAssessment, InfringementRisk, DesignAroundStrategy]:
        """Parse OpenAI response into structured sections (JSON or Markdown fallback)."""
        
        # 1. Try JSON parsing
        try:
            # Clean possible markdown code blocks
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            
            data = json.loads(clean_response)
            
            # Helper to safely get nested keys
            def get_val(d, keys, default=None):
                for k in keys:
                    if isinstance(d, dict):
                        d = d.get(k, default)
                    else:
                        return default
                return d

            # Similarity
            sim_data = data.get("유사도 평가", {})
            similarity = SimilarityAssessment(
                score=int(str(sim_data.get("기술적 유사성 점수", "0")).replace("점", "").split("/")[0].strip()),
                common_elements=sim_data.get("핵심 공통 기술 요소", []),
                summary=str(sim_data)
            )

            # Infringement
            risk_data = data.get("침해 리스크", {})
            infringement = InfringementRisk(
                risk_level=risk_data.get("리스크 수준", "unknown").lower(),
                risk_factors=[risk_data.get("위험 요소", "")] if isinstance(risk_data.get("위험 요소"), str) else risk_data.get("위험 요소", []),
                summary=str(risk_data)
            )

            # Design Around
            design_data = data.get("회피 전략", {})
            design_around = DesignAroundStrategy(
                strategies=[design_data.get("분석 대상 특허가 선행 기술을 회피하기 위해 수정해야 할 구체적인 설계 변경 제안", "")] if isinstance(design_data.get("분석 대상 특허가 선행 기술을 회피하기 위해 수정해야 할 구체적인 설계 변경 제안"), str) else design_data.get("분석 대상 특허가 선행 기술을 회피하기 위해 수정해야 할 구체적인 설계 변경 제안", []),
                alternative_approaches=[design_data.get("구성요소의 삭제, 치환, 변경을 포함한 실질적 조언", "")] if isinstance(design_data.get("구성요소의 삭제, 치환, 변경을 포함한 실질적 조언"), str) else design_data.get("구성요소의 삭제, 치환, 변경을 포함한 실질적 조언", []),
                summary=str(design_data)
            )

            return similarity, infringement, design_around

        except json.JSONDecodeError:
            logger.warning("JSON parsing failed, falling back to regex parsing")
            # Fallback to regex if JSON fails
            similarity = self._extract_similarity(response)
            infringement = self._extract_infringement(response)
            design_around = self._extract_design_around(response)
            
            return similarity, infringement, design_around
    
    def _extract_similarity(self, response: str) -> SimilarityAssessment:
        """Extract 유사도 평가 section."""
        # Find section
        pattern = r'\[유사도 평가\](.*?)(?=\[침해 리스크\]|\[회피 전략\]|$)'
        match = re.search(pattern, response, re.DOTALL)
        
        if not match:
            return SimilarityAssessment(0, [], "Section not found")
        
        section = match.group(1).strip()
        
        # Extract score
        score_match = re.search(r'(\d{1,3})\s*(?:점|%|/100)?', section)
        score = int(score_match.group(1)) if score_match else 0
        score = min(100, max(0, score))  # Clamp to 0-100
        
        # Extract common elements (bullet points)
        elements = re.findall(r'[-•]\s*(.+?)(?=\n|$)', section)
        
        return SimilarityAssessment(
            score=score,
            common_elements=elements[:5],  # Top 5
            summary=section[:500],
        )
    
    def _extract_infringement(self, response: str) -> InfringementRisk:
        """Extract 침해 리스크 section."""
        pattern = r'\[침해 리스크\](.*?)(?=\[회피 전략\]|$)'
        match = re.search(pattern, response, re.DOTALL)
        
        if not match:
            return InfringementRisk("unknown", [], "Section not found")
        
        section = match.group(1).strip()
        
        # Determine risk level
        section_lower = section.lower()
        if any(w in section_lower for w in ['높', 'high', '심각', 'significant']):
            risk_level = "high"
        elif any(w in section_lower for w in ['중간', 'medium', 'moderate', '보통']):
            risk_level = "medium"
        elif any(w in section_lower for w in ['낮', 'low', '미미', 'minor']):
            risk_level = "low"
        else:
            risk_level = "medium"  # Default
        
        # Extract risk factors
        factors = re.findall(r'[-•]\s*(.+?)(?=\n|$)', section)
        
        return InfringementRisk(
            risk_level=risk_level,
            risk_factors=factors[:5],
            summary=section[:500],
        )
    
    def _extract_design_around(self, response: str) -> DesignAroundStrategy:
        """Extract 회피 전략 section."""
        pattern = r'\[회피 전략\](.*?)$'
        match = re.search(pattern, response, re.DOTALL)
        
        if not match:
            return DesignAroundStrategy([], [], "Section not found")
        
        section = match.group(1).strip()
        
        # Extract strategies and alternatives
        items = re.findall(r'[-•]\s*(.+?)(?=\n|$)', section)
        
        # Split into strategies and alternatives (rough heuristic)
        strategies = [i for i in items if '대안' not in i.lower()][:3]
        alternatives = [i for i in items if '대안' in i.lower()][:3]
        
        if not alternatives and len(strategies) > 3:
            alternatives = strategies[3:]
            strategies = strategies[:3]
        
        return DesignAroundStrategy(
            strategies=strategies,
            alternative_approaches=alternatives,
            summary=section[:500],
        )


# =============================================================================
# Self-RAG Training Data Generator
# =============================================================================

class SelfRAGDataGenerator:
    """
    Generate training data for Self-RAG from patent citations.
    
    Creates pairs of:
    - Query (question about patent similarity/infringement)
    - Context (anchor and cited claims)
    - Ground Truth (OpenAI-generated critique)
    """
    
    def __init__(
        self,
        self_rag_config: SelfRAGConfig = config.self_rag,
    ):
        self.config = self_rag_config
        self.critique_generator = None
        
        if OPENAI_AVAILABLE and self.config.openai_api_key:
            try:
                self.critique_generator = OpenAICritiqueGenerator(self_rag_config)
            except Exception as e:
                logger.warning(f"Could not initialize critique generator: {e}")
    
    async def generate_training_samples(
        self,
        processed_patents: List[Dict[str, Any]],
        output_path: Optional[Path] = None,
    ) -> List[SelfRAGTrainingSample]:
        """
        Generate Self-RAG training samples from processed patents.
        
        Args:
            processed_patents: List of processed patent dictionaries
            output_path: Optional path to save samples
            
        Returns:
            List of SelfRAGTrainingSample objects
        """
        if not self.critique_generator:
            logger.error("Critique generator not available. Check API key.")
            return []
        
        samples = []
        
        # Build citation pairs
        citation_pairs = self._build_citation_pairs(processed_patents)
        logger.info(f"Found {len(citation_pairs)} citation pairs for analysis")
        
        # Limit pairs
        max_pairs = len(processed_patents) * self.config.max_pairs_per_patent
        citation_pairs = citation_pairs[:max_pairs]
        
        # Generate critiques
        for anchor, cited in tqdm(citation_pairs, desc="Generating critiques"):
            try:
                # Generate critique
                critique = await self.critique_generator.generate_critique(
                    anchor_id=anchor["publication_number"],
                    anchor_claim=anchor["claim_text"],
                    cited_id=cited["publication_number"],
                    cited_claim=cited["claim_text"],
                )
                
                # Create training sample
                sample = self._create_training_sample(anchor, cited, critique)
                samples.append(sample)
                print(f" ✅ Generated: {anchor['publication_number']} vs {cited['publication_number']} (Score: {critique.similarity.score})")
                
                # Rate limiting (avoid API throttling)
                await asyncio.sleep(0.5)  # OpenAI has higher rate limits than Gemini
                
            except Exception as e:
                print(f"\n❌ Error processing pair {anchor['publication_number']}: {e}")
                logger.error(f"Error processing pair {anchor['publication_number']}-{cited['publication_number']}: {e}")
                continue
        
        # Save if path provided
        if output_path:
            self._save_samples(samples, output_path)
        
        return samples
    
    def _build_citation_pairs(
        self,
        processed_patents: List[Dict[str, Any]],
    ) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """Build pairs of patents for comparison (IPC-based since citations are external)."""
        pairs = []
        
        # Group patents by IPC code
        ipc_groups: Dict[str, List[Dict[str, Any]]] = {}
        
        for patent in processed_patents:
            ipc_codes = patent.get("ipc_codes", [])
            if not ipc_codes:
                continue
            
            # Use first 4 chars of IPC as group key
            ipc_key = ipc_codes[0][:4] if len(ipc_codes[0]) >= 4 else ipc_codes[0]
            
            # Get text for comparison (abstract or claims)
            text = patent.get("abstract", "")
            if not text:
                claims = patent.get("claims", [])
                if claims and isinstance(claims[0], dict):
                    text = claims[0].get("claim_text", "")
            
            if text and len(text) > 100:  # Minimum text length
                if ipc_key not in ipc_groups:
                    ipc_groups[ipc_key] = []
                ipc_groups[ipc_key].append({
                    "publication_number": patent.get("publication_number", ""),
                    "claim_text": text,
                    "ipc_code": ipc_codes[0] if ipc_codes else "",
                    "rag_components": [],
                })
        
        # Build pairs from same IPC group
        import random
        
        for ipc_key, patents in ipc_groups.items():
            if len(patents) < 2:
                continue
            
            # Sample pairs from each IPC group (max 3 pairs per group)
            for i, anchor in enumerate(patents[:min(10, len(patents))]):
                # Find a different patent in same group
                candidates = [p for j, p in enumerate(patents) if j != i]
                if candidates:
                    compared = random.choice(candidates)
                    pairs.append((anchor, compared))
                    
                    if len(pairs) >= self.config.max_pairs_per_patent * 100:
                        break
            
            if len(pairs) >= self.config.max_pairs_per_patent * 100:
                break
        
        return pairs
    
    def _create_training_sample(
        self,
        anchor: Dict[str, Any],
        cited: Dict[str, Any],
        critique: CritiqueResult,
    ) -> SelfRAGTrainingSample:
        """Create a training sample from critique result."""
        
        # Generate query
        query = f"""특허 {anchor['publication_number']}의 청구항과 선행특허 {cited['publication_number']}의 
청구항을 비교 분석하세요. 유사도, 침해 리스크, 회피 전략을 포함해서 답변해주세요."""
        
        # Format ground truth
        ground_truth = f"""[유사도 평가]
- 기술적 유사성 점수: {critique.similarity.score}/100
- 핵심 공통 요소: {', '.join(critique.similarity.common_elements[:3]) if critique.similarity.common_elements else '없음'}
{critique.similarity.summary}

[침해 리스크]
- 리스크 수준: {critique.infringement.risk_level}
- 위험 요소: {', '.join(critique.infringement.risk_factors[:3]) if critique.infringement.risk_factors else '없음'}
{critique.infringement.summary}

[회피 전략]
- 설계 변경: {', '.join(critique.design_around.strategies[:3]) if critique.design_around.strategies else '없음'}
- 대안적 접근: {', '.join(critique.design_around.alternative_approaches[:3]) if critique.design_around.alternative_approaches else '없음'}
{critique.design_around.summary}"""
        
        return SelfRAGTrainingSample(
            sample_id=f"{anchor['publication_number']}_{cited['publication_number']}",
            query=query,
            anchor_patent_id=anchor["publication_number"],
            anchor_claim=anchor["claim_text"][:2000],
            cited_patent_id=cited["publication_number"],
            cited_claim=cited["claim_text"][:2000],
            ground_truth_critique=ground_truth,
            similarity_score=critique.similarity.score,
            risk_level=critique.infringement.risk_level,
            rag_components_anchor=anchor.get("rag_components", []),
            rag_components_cited=cited.get("rag_components", []),
        )
    
    def _save_samples(
        self,
        samples: List[SelfRAGTrainingSample],
        output_path: Path,
    ) -> None:
        """Save training samples to file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = [asdict(s) for s in samples]
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(samples)} training samples to: {output_path}")


# =============================================================================
# CLI Entry Point
# =============================================================================

async def main():
    """Generate Self-RAG training data."""
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format=config.logging.log_format,
    )
    
    print("\n" + "=" * 70)
    print("⚡ 쇼특허 (Short-Cut) v3.0 - Self-RAG Training Data Generator")
    print("=" * 70)
    
    if not OPENAI_AVAILABLE:
        print("❌ openai not installed.")
        print("   Install with: pip install openai")
        return
    
    if not config.self_rag.openai_api_key:
        print("❌ OPENAI_API_KEY not set.")
        print("   Set via .env file or: export OPENAI_API_KEY=your-api-key")
        return
    
    # Check for input file
    if len(sys.argv) < 2:
        processed_files = list(PROCESSED_DATA_DIR.glob("processed_*.json"))
        if not processed_files:
            print("❌ No processed patent data found.")
            return
        input_path = max(processed_files, key=lambda p: p.stat().st_mtime)
    else:
        input_path = Path(sys.argv[1])
    
    print(f"📂 Input: {input_path}")
    
    # Load data
    with open(input_path, 'r', encoding='utf-8') as f:
        processed_patents = json.load(f)
    
    print(f"📊 Loaded {len(processed_patents)} processed patents")
    
    # Generate training data
    generator = SelfRAGDataGenerator()
    
    output_path = PROCESSED_DATA_DIR / f"selfrag_training_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    samples = await generator.generate_training_samples(
        processed_patents,
        output_path,
    )
    
    print(f"\n✅ Generation complete!")
    print(f"   Samples: {len(samples)}")
    print(f"   Output: {output_path}")
    
    # Show sample
    if samples:
        print(f"\n📝 Sample output:")
        print(f"   Query: {samples[0].query[:100]}...")
        print(f"   Similarity: {samples[0].similarity_score}/100")
        print(f"   Risk: {samples[0].risk_level}")


if __name__ == "__main__":
    asyncio.run(main())
