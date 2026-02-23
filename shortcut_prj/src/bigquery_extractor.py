"""
Short-Cut v3.0 - BigQuery Data Extractor
============================================
Extracts patent data from Google Patents Public Dataset with cost optimization.

Features:
- Domain-targeted SQL generation
- Cost estimation via dry run
- Filing date partitioning for efficiency
- Async batch processing

Author: Team 뀨💕
License: MIT
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, AsyncGenerator
from dataclasses import dataclass

from google.cloud import bigquery
from google.cloud.bigquery import QueryJobConfig
from tqdm import tqdm

from src.config import config, BigQueryConfig, DomainConfig

# =============================================================================
# Logging Setup
# =============================================================================

logger = logging.getLogger(__name__)


# =============================================================================
# SQL Query Templates
# =============================================================================

# Main patent extraction query with citation data
PATENT_EXTRACTION_SQL = """
-- Short-Cut v3.0: RAG/sLLM Domain Patent Extraction
-- Generated: {generated_at}
-- Domain: {domain_name}

WITH FilteredPatents AS (
    SELECT
        publication_number,
        application_number,
        country_code,
        family_id,
        
        -- Dates for sorting (newest first) - Handle NULL/0 values
        SAFE.PARSE_DATE('%Y%m%d', CAST(NULLIF(filing_date, 0) AS STRING)) AS filing_date_parsed,
        SAFE.PARSE_DATE('%Y%m%d', CAST(NULLIF(grant_date, 0) AS STRING)) AS grant_date_parsed,
        SAFE.PARSE_DATE('%Y%m%d', CAST(NULLIF(priority_date, 0) AS STRING)) AS priority_date_parsed,
        
        -- Text content (English preferred)
        (SELECT text FROM UNNEST(title_localized) WHERE language = 'en' LIMIT 1) AS title_en,
        (SELECT text FROM UNNEST(abstract_localized) WHERE language = 'en' LIMIT 1) AS abstract_en,
        
        -- Full arrays for multilingual support (description excluded for cost)
        title_localized,
        abstract_localized,
        claims_localized,
        -- description_localized,  -- EXCLUDED: Too large, ~50% of scan cost!
        
        -- Classification codes
        ipc,
        cpc,
        
        -- Citations (for PAI-NET)
        citation,
        
        -- Inventor and assignee info
        inventor_harmonized,
        assignee_harmonized
        
    FROM {full_table_name}
    
    WHERE
        -- Date range filter (partitioning optimization)
        filing_date >= {min_filing_date}
        AND filing_date <= {max_filing_date}
        
        -- Country filter (major patent offices)
        AND country_code IN ('US', 'EP', 'WO', 'CN', 'JP', 'KR')
        
        -- Keyword OR IPC matching (either condition is enough)
        AND (
            -- Keyword matching in title/abstract
            (
                {keyword_conditions}
            )
            OR
            -- IPC/CPC code matching
            (
                {ipc_conditions}
            )
        )
)

SELECT
    fp.*,
    
    -- Citation statistics
    ARRAY_LENGTH(fp.citation) AS citation_count,
    
    -- Extract cited publication numbers
    ARRAY(
        SELECT DISTINCT c.publication_number 
        FROM UNNEST(fp.citation) AS c 
        WHERE c.publication_number IS NOT NULL
    ) AS cited_publications,
    
    -- Calculate importance score based on citations
    ARRAY_LENGTH(fp.citation) * 1.0 AS importance_score

FROM FilteredPatents fp

ORDER BY 
    fp.filing_date_parsed DESC,
    importance_score DESC

{limit_clause}
"""


# Query for citation network (PAI-NET)
CITATION_NETWORK_SQL = """
-- PAI-NET Citation Network Extraction
-- Get bidirectional citation relationships

WITH AnchorsAndCitations AS (
    SELECT
        p.publication_number AS anchor_id,
        c.publication_number AS cited_id,
        c.category AS citation_type,  -- 'A', 'D', 'X', 'Y', etc.
        (SELECT text FROM UNNEST(p.ipc) LIMIT 1).code AS anchor_ipc
    FROM {full_table_name} p,
    UNNEST(p.citation) AS c
    WHERE 
        p.publication_number IN ({anchor_ids})
        AND c.publication_number IS NOT NULL
)

SELECT 
    ac.anchor_id,
    ac.cited_id,
    ac.citation_type,
    ac.anchor_ipc,
    
    -- Get cited patent's basic info
    cp.title_localized,
    cp.abstract_localized,
    cp.claims_localized,
    (SELECT code FROM UNNEST(cp.ipc) LIMIT 1) AS cited_ipc

FROM AnchorsAndCitations ac
LEFT JOIN {full_table_name} cp 
    ON ac.cited_id = cp.publication_number
"""


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class QueryCostEstimate:
    """BigQuery cost estimation result."""
    total_bytes_processed: int
    total_bytes_billed: int
    estimated_cost_usd: float
    query_plan: Optional[str] = None
    
    def __str__(self) -> str:
        gb_processed = self.total_bytes_processed / (1024**3)
        return (
            f"Query Cost Estimate:\n"
            f"  Bytes Processed: {gb_processed:.2f} GB\n"
            f"  Estimated Cost: ${self.estimated_cost_usd:.4f} USD"
        )


@dataclass  
class ExtractionResult:
    """Result of patent data extraction."""
    success: bool
    patents_count: int
    output_path: Optional[Path]
    cost_estimate: Optional[QueryCostEstimate]
    error_message: Optional[str] = None


# =============================================================================
# SQL Generator
# =============================================================================

class SQLGenerator:
    """Generate domain-targeted BigQuery SQL."""
    
    def __init__(
        self, 
        bq_config: BigQueryConfig = config.bigquery,
        domain_config: DomainConfig = config.domain,
    ):
        self.bq_config = bq_config
        self.domain_config = domain_config
    
    def _build_keyword_conditions(self) -> str:
        """Build SQL OR conditions for keyword matching."""
        conditions = []
        
        for keyword in self.domain_config.keywords:
            # Escape single quotes in keywords
            escaped = keyword.replace("'", "\\'")
            conditions.append(f"""
                REGEXP_CONTAINS(
                    LOWER(COALESCE(
                        (SELECT text FROM UNNEST(title_localized) WHERE language = 'en' LIMIT 1),
                        ''
                    ) || ' ' || COALESCE(
                        (SELECT text FROM UNNEST(abstract_localized) WHERE language = 'en' LIMIT 1),
                        ''
                    )),
                    r'(?i){escaped}'
                )
            """)
        
        return "\n            OR ".join(conditions)
    
    def _build_ipc_conditions(self) -> str:
        """Build SQL conditions for IPC/CPC code matching."""
        conditions = []
        
        for ipc_code in self.domain_config.ipc_codes:
            # Match IPC codes at the start
            conditions.append(f"""
                EXISTS(
                    SELECT 1 FROM UNNEST(ipc) AS i 
                    WHERE STARTS_WITH(i.code, '{ipc_code}')
                )
            """)
            conditions.append(f"""
                EXISTS(
                    SELECT 1 FROM UNNEST(cpc) AS c 
                    WHERE STARTS_WITH(c.code, '{ipc_code}')
                )
            """)
        
        return "\n            OR ".join(conditions)
    
    def generate_extraction_sql(self, limit: Optional[int] = None) -> str:
        """Generate the main patent extraction SQL query."""
        
        limit_clause = f"LIMIT {limit}" if limit else ""
        if self.bq_config.max_results and not limit:
            limit_clause = f"LIMIT {self.bq_config.max_results}"
        
        sql = PATENT_EXTRACTION_SQL.format(
            generated_at=datetime.now().isoformat(),
            domain_name=self.domain_config.domain_name,
            full_table_name=self.bq_config.full_table_name,
            min_filing_date=self.bq_config.min_filing_date.replace("-", ""),
            max_filing_date=self.bq_config.max_filing_date.replace("-", ""),
            keyword_conditions=self._build_keyword_conditions(),
            ipc_conditions=self._build_ipc_conditions(),
            limit_clause=limit_clause,
        )
        
        return sql
    
    def generate_citation_network_sql(self, anchor_ids: List[str]) -> str:
        """Generate SQL for citation network extraction."""
        
        ids_string = ", ".join([f"'{id}'" for id in anchor_ids])
        
        sql = CITATION_NETWORK_SQL.format(
            full_table_name=self.bq_config.full_table_name,
            anchor_ids=ids_string,
        )
        
        return sql
    
    def save_generated_sql(self, sql: str, filename: str = "generated_query.sql") -> Path:
        """Save generated SQL to file for review."""
        from src.config import DATA_DIR
        
        sql_dir = DATA_DIR / "sql"
        sql_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = sql_dir / filename
        output_path.write_text(sql, encoding="utf-8")
        
        logger.info(f"SQL saved to: {output_path}")
        return output_path


# =============================================================================
# BigQuery Extractor
# =============================================================================

class BigQueryExtractor:
    """Extract patent data from BigQuery with cost optimization."""
    
    def __init__(
        self,
        bq_config: BigQueryConfig = config.bigquery,
        domain_config: DomainConfig = config.domain,
    ):
        self.bq_config = bq_config
        self.domain_config = domain_config
        self.client = bigquery.Client(project=bq_config.project_id)
        self.sql_generator = SQLGenerator(bq_config, domain_config)
    
    async def estimate_query_cost(self, sql: str) -> QueryCostEstimate:
        """
        Estimate query cost using dry run.
        
        Args:
            sql: SQL query to estimate
            
        Returns:
            QueryCostEstimate with bytes and cost info
        """
        job_config = QueryJobConfig(dry_run=True, use_query_cache=False)
        
        loop = asyncio.get_event_loop()
        query_job = await loop.run_in_executor(
            None,
            lambda: self.client.query(sql, job_config=job_config)
        )
        
        bytes_processed = query_job.total_bytes_processed
        bytes_billed = query_job.total_bytes_billed or bytes_processed
        
        # BigQuery pricing: $5 per TB
        cost_per_tb = 5.0
        estimated_cost = (bytes_billed / (1024**4)) * cost_per_tb
        
        return QueryCostEstimate(
            total_bytes_processed=bytes_processed,
            total_bytes_billed=bytes_billed,
            estimated_cost_usd=estimated_cost,
        )
    
    async def execute_query(
        self, 
        sql: str,
        output_path: Optional[Path] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute query and return results.
        
        Args:
            sql: SQL query to execute
            output_path: Optional path to save results as JSON
            
        Returns:
            List of patent records
        """
        logger.info("Executing BigQuery query...")
        
        job_config = QueryJobConfig(use_query_cache=self.bq_config.use_query_cache)
        
        loop = asyncio.get_event_loop()
        query_job = await loop.run_in_executor(
            None,
            lambda: self.client.query(sql, job_config=job_config)
        )
        
        # Stream results with progress
        results = []
        total_rows = query_job.result().total_rows
        
        logger.info(f"Processing {total_rows} patents...")
        
        for row in tqdm(query_job.result(), total=total_rows, desc="Fetching patents"):
            record = dict(row)
            # Convert non-serializable types
            record = self._serialize_record(record)
            results.append(record)
        
        # Save to file if path provided
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved {len(results)} patents to: {output_path}")
        
        return results
    
    def _serialize_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Convert non-JSON-serializable types."""
        serialized = {}
        
        for key, value in record.items():
            if value is None:
                serialized[key] = None
            elif isinstance(value, (list, tuple)):
                serialized[key] = [self._serialize_value(v) for v in value]
            elif hasattr(value, '__dict__'):
                serialized[key] = dict(value)
            else:
                serialized[key] = self._serialize_value(value)
        
        return serialized
    
    def _serialize_value(self, value: Any) -> Any:
        """Serialize a single value."""
        from datetime import date
        
        if value is None:
            return None
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, date):
            return value.isoformat()
        elif hasattr(value, 'isoformat'):
            return value.isoformat()
        elif hasattr(value, '__dict__'):
            return dict(value)
        else:
            return value
    
    async def extract_patents(
        self,
        limit: Optional[int] = None,
        dry_run_first: bool = True,
    ) -> ExtractionResult:
        """
        Main extraction pipeline.
        
        Args:
            limit: Optional limit on number of patents
            dry_run_first: Whether to estimate cost before executing
            
        Returns:
            ExtractionResult with extraction status and output path
        """
        from src.config import RAW_DATA_DIR
        
        try:
            # Generate SQL
            sql = self.sql_generator.generate_extraction_sql(limit=limit)
            
            # Save SQL for review
            sql_path = self.sql_generator.save_generated_sql(
                sql, 
                f"extraction_{self.domain_config.domain_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
            )
            logger.info(f"Generated SQL saved to: {sql_path}")
            
            # Cost estimation
            cost_estimate = None
            if dry_run_first or self.bq_config.dry_run:
                logger.info("Running cost estimation (dry run)...")
                cost_estimate = await self.estimate_query_cost(sql)
                logger.info(str(cost_estimate))
                
                if self.bq_config.dry_run:
                    logger.info("Dry run mode - skipping actual query execution")
                    return ExtractionResult(
                        success=True,
                        patents_count=0,
                        output_path=None,
                        cost_estimate=cost_estimate,
                    )
            
            # Execute query
            output_path = RAW_DATA_DIR / f"patents_{self.domain_config.domain_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            patents = await self.execute_query(sql, output_path)
            
            return ExtractionResult(
                success=True,
                patents_count=len(patents),
                output_path=output_path,
                cost_estimate=cost_estimate,
            )
            
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return ExtractionResult(
                success=False,
                patents_count=0,
                output_path=None,
                cost_estimate=None,
                error_message=str(e),
            )
    
    async def extract_citation_network(
        self,
        anchor_publication_numbers: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Extract citation network for given anchor patents.
        
        Args:
            anchor_publication_numbers: List of publication numbers
            
        Returns:
            List of citation relationship records
        """
        logger.info(f"Extracting citation network for {len(anchor_publication_numbers)} anchors...")
        
        # Process in batches to avoid query size limits
        all_citations = []
        batch_size = 100
        
        for i in tqdm(range(0, len(anchor_publication_numbers), batch_size), desc="Citation batches"):
            batch_ids = anchor_publication_numbers[i:i+batch_size]
            sql = self.sql_generator.generate_citation_network_sql(batch_ids)
            
            citations = await self.execute_query(sql)
            all_citations.extend(citations)
        
        logger.info(f"Extracted {len(all_citations)} citation relationships")
        return all_citations


# =============================================================================
# CLI Entry Point
# =============================================================================

async def main():
    """Main entry point for standalone execution."""
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format=config.logging.log_format,
    )
    
    print("\n" + "=" * 70)
    print("⚡ 쇼특허 (Short-Cut) v3.0 - BigQuery Data Extractor")
    print("=" * 70)
    
    # Initialize extractor
    extractor = BigQueryExtractor()
    
    # Check for command line args
    limit = 100  # Default to small batch for testing
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            pass
    
    print(f"\n📊 Extraction Settings:")
    print(f"   Domain: {config.domain.domain_name}")
    print(f"   Date Range: {config.bigquery.min_filing_date} ~ {config.bigquery.max_filing_date}")
    print(f"   Limit: {limit}")
    print(f"   Dry Run: {config.bigquery.dry_run}")
    
    # Run extraction
    result = await extractor.extract_patents(limit=limit)
    
    if result.success:
        print(f"\n✅ Extraction completed!")
        print(f"   Patents: {result.patents_count}")
        if result.output_path:
            print(f"   Output: {result.output_path}")
        if result.cost_estimate:
            print(f"   {result.cost_estimate}")
    else:
        print(f"\n❌ Extraction failed: {result.error_message}")


if __name__ == "__main__":
    asyncio.run(main())
