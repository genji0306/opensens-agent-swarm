"""Academic source search — arXiv, Semantic Scholar, bioRxiv.

Provides a unified interface for searching academic papers across
multiple databases. Results are normalised into a common format.
"""
from __future__ import annotations

import logging
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

__all__ = ["AcademicSearcher", "SearchResult"]

logger = logging.getLogger("oas.deep_research.sources")

try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False


@dataclass
class SearchResult:
    """A single search result from any academic source."""

    title: str
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    url: str = ""
    doi: str = ""
    source: str = ""  # "arxiv" | "semantic_scholar" | "biorxiv"
    year: int | None = None
    citation_count: int = 0
    is_peer_reviewed: bool = False


class AcademicSearcher:
    """Searches academic databases for papers relevant to a topic.

    Supports arXiv, Semantic Scholar, and bioRxiv. Each source is optional
    and fails gracefully if unavailable.
    """

    def __init__(
        self,
        *,
        arxiv_max: int = 10,
        semantic_scholar_max: int = 10,
        biorxiv_enabled: bool = True,
        pubmed_enabled: bool = True,
        openalex_enabled: bool = True,
        crossref_enabled: bool = True,
        core_enabled: bool = True,
        europepmc_enabled: bool = True,
        doaj_enabled: bool = True,
        timeout: float = 15.0,
    ):
        self.arxiv_max = arxiv_max
        self.semantic_scholar_max = semantic_scholar_max
        self.biorxiv_enabled = biorxiv_enabled
        self.pubmed_enabled = pubmed_enabled
        self.openalex_enabled = openalex_enabled
        self.crossref_enabled = crossref_enabled
        self.core_enabled = core_enabled
        self.europepmc_enabled = europepmc_enabled
        self.doaj_enabled = doaj_enabled
        self.timeout = timeout

    async def search_all(self, query: str) -> list[SearchResult]:
        """Search all configured academic sources in parallel (up to 9 databases)."""
        results: list[SearchResult] = []

        # Run searches concurrently
        import asyncio
        tasks = [
            self.search_arxiv(query),
            self.search_semantic_scholar(query),
        ]
        if self.biorxiv_enabled:
            tasks.append(self.search_biorxiv(query))
        if self.pubmed_enabled:
            tasks.append(self.search_pubmed(query))
        if self.openalex_enabled:
            tasks.append(self.search_openalex(query))
        if self.crossref_enabled:
            tasks.append(self.search_crossref(query))
        if self.europepmc_enabled:
            tasks.append(self.search_europepmc(query))

        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for batch in gathered:
            if isinstance(batch, list):
                results.extend(batch)
            elif isinstance(batch, Exception):
                logger.warning("source_search_error: %s", str(batch))

        # Deduplicate by DOI
        seen_dois: set[str] = set()
        unique: list[SearchResult] = []
        for r in results:
            if r.doi and r.doi in seen_dois:
                continue
            if r.doi:
                seen_dois.add(r.doi)
            unique.append(r)

        logger.info("academic_search_complete: query=%s results=%d", query[:80], len(unique))
        return unique

    async def search_arxiv(self, query: str) -> list[SearchResult]:
        """Search arXiv via its public API."""
        if not _AIOHTTP_AVAILABLE:
            return []

        encoded = urllib.parse.quote(query)
        url = (
            f"http://export.arxiv.org/api/query?"
            f"search_query=all:{encoded}&start=0&max_results={self.arxiv_max}"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                    if resp.status != 200:
                        return []
                    text = await resp.text()
                    return self._parse_arxiv_atom(text)
        except Exception as exc:
            logger.warning("arxiv_search_failed: %s", exc)
            return []

    def _parse_arxiv_atom(self, xml_text: str) -> list[SearchResult]:
        """Parse arXiv Atom XML into SearchResults."""
        import xml.etree.ElementTree as ET

        results: list[SearchResult] = []
        try:
            root = ET.fromstring(xml_text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall("atom:entry", ns):
                title = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
                abstract = (entry.findtext("atom:summary", "", ns) or "").strip().replace("\n", " ")
                authors = [
                    a.findtext("atom:name", "", ns)
                    for a in entry.findall("atom:author", ns)
                ]
                # Get the abstract link
                link = ""
                for l_elem in entry.findall("atom:link", ns):
                    if l_elem.get("type") == "text/html":
                        link = l_elem.get("href", "")
                        break
                if not link:
                    link_elem = entry.find("atom:id", ns)
                    link = link_elem.text if link_elem is not None else ""

                # Extract year from published date
                published = entry.findtext("atom:published", "", ns)
                year = int(published[:4]) if published and len(published) >= 4 else None

                results.append(SearchResult(
                    title=title,
                    authors=[a for a in authors if a],
                    abstract=abstract[:500],
                    url=link,
                    source="arxiv",
                    year=year,
                    is_peer_reviewed=False,
                ))
        except ET.ParseError:
            logger.warning("arxiv_xml_parse_error")

        return results

    async def search_semantic_scholar(self, query: str) -> list[SearchResult]:
        """Search Semantic Scholar via its public API."""
        if not _AIOHTTP_AVAILABLE:
            return []

        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": query,
            "limit": self.semantic_scholar_max,
            "fields": "title,authors,abstract,url,externalIds,year,citationCount,isOpenAccess",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    papers = data.get("data", [])

                    results: list[SearchResult] = []
                    for p in papers:
                        authors = [a.get("name", "") for a in (p.get("authors") or [])]
                        ext_ids = p.get("externalIds") or {}
                        results.append(SearchResult(
                            title=p.get("title", ""),
                            authors=authors,
                            abstract=(p.get("abstract") or "")[:500],
                            url=p.get("url", ""),
                            doi=ext_ids.get("DOI", ""),
                            source="semantic_scholar",
                            year=p.get("year"),
                            citation_count=p.get("citationCount", 0),
                            is_peer_reviewed=bool(ext_ids.get("DOI")),
                        ))
                    return results
        except Exception as exc:
            logger.warning("semantic_scholar_search_failed: %s", exc)
            return []

    async def search_biorxiv(self, query: str) -> list[SearchResult]:
        """Search bioRxiv/medRxiv via their API."""
        if not _AIOHTTP_AVAILABLE:
            return []

        # bioRxiv detail endpoint (recent papers, filter by content match)
        # The public API provides date-based listing, not keyword search
        # We use a simplified approach: recent 30 days, filter locally
        import datetime
        end = datetime.date.today()
        start = end - datetime.timedelta(days=30)
        url = f"https://api.biorxiv.org/details/biorxiv/{start.isoformat()}/{end.isoformat()}/0/25"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    papers = data.get("collection", [])

                    query_lower = query.lower()
                    results: list[SearchResult] = []
                    for p in papers:
                        title = p.get("title", "")
                        abstract = p.get("abstract", "")
                        # Simple keyword match
                        if any(kw in (title + abstract).lower() for kw in query_lower.split()[:3]):
                            results.append(SearchResult(
                                title=title,
                                authors=p.get("authors", "").split("; ") if p.get("authors") else [],
                                abstract=abstract[:500],
                                url=f"https://doi.org/{p.get('doi', '')}",
                                doi=p.get("doi", ""),
                                source="biorxiv",
                                year=int(p.get("date", "2026")[:4]) if p.get("date") else None,
                                is_peer_reviewed=False,
                            ))
                    return results[:5]
        except Exception as exc:
            logger.warning("biorxiv_search_failed: %s", exc)
            return []

    async def search_pubmed(self, query: str) -> list[SearchResult]:
        """Search PubMed via NCBI E-utilities API."""
        if not _AIOHTTP_AVAILABLE:
            return []

        encoded = urllib.parse.quote(query)
        search_url = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
            f"db=pubmed&term={encoded}&retmax=10&retmode=json"
        )

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: Get PMIDs
                async with session.get(search_url, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    pmids = data.get("esearchresult", {}).get("idlist", [])
                    if not pmids:
                        return []

                # Step 2: Fetch summaries
                ids = ",".join(pmids[:10])
                summary_url = (
                    f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"
                    f"db=pubmed&id={ids}&retmode=json"
                )
                async with session.get(summary_url, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    result_map = data.get("result", {})

                    results: list[SearchResult] = []
                    for pmid in pmids[:10]:
                        entry = result_map.get(pmid, {})
                        if not isinstance(entry, dict):
                            continue
                        authors = [a.get("name", "") for a in entry.get("authors", [])]
                        pub_date = entry.get("pubdate", "")
                        year = int(pub_date[:4]) if pub_date and len(pub_date) >= 4 else None
                        doi_list = entry.get("articleids", [])
                        doi = ""
                        for aid in doi_list:
                            if aid.get("idtype") == "doi":
                                doi = aid.get("value", "")
                                break
                        results.append(SearchResult(
                            title=entry.get("title", ""),
                            authors=authors,
                            abstract="",  # Summaries don't include abstracts
                            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                            doi=doi,
                            source="pubmed",
                            year=year,
                            is_peer_reviewed=True,
                        ))
                    return results
        except Exception as exc:
            logger.warning("pubmed_search_failed: %s", exc)
            return []

    async def search_openalex(self, query: str) -> list[SearchResult]:
        """Search OpenAlex (250M+ works, open metadata)."""
        if not _AIOHTTP_AVAILABLE:
            return []

        url = "https://api.openalex.org/works"
        params = {
            "search": query,
            "per_page": 10,
            "select": "title,authorships,doi,publication_year,cited_by_count,open_access,abstract_inverted_index",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers={"User-Agent": "mailto:steve@opensens.io"},
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    works = data.get("results", [])

                    results: list[SearchResult] = []
                    for w in works:
                        authors = [
                            a.get("author", {}).get("display_name", "")
                            for a in (w.get("authorships") or [])
                        ]
                        # Reconstruct abstract from inverted index
                        abstract = ""
                        aii = w.get("abstract_inverted_index")
                        if aii and isinstance(aii, dict):
                            # Build word→position map, sort by position
                            words: list[tuple[int, str]] = []
                            for word, positions in aii.items():
                                for pos in positions:
                                    words.append((pos, word))
                            words.sort()
                            abstract = " ".join(w for _, w in words)[:500]

                        doi = w.get("doi", "") or ""
                        if doi.startswith("https://doi.org/"):
                            doi = doi[len("https://doi.org/"):]

                        results.append(SearchResult(
                            title=w.get("title", ""),
                            authors=[a for a in authors if a][:5],
                            abstract=abstract,
                            url=w.get("doi", ""),
                            doi=doi,
                            source="openalex",
                            year=w.get("publication_year"),
                            citation_count=w.get("cited_by_count", 0),
                            is_peer_reviewed=bool(doi),
                        ))
                    return results
        except Exception as exc:
            logger.warning("openalex_search_failed: %s", exc)
            return []

    async def search_crossref(self, query: str) -> list[SearchResult]:
        """Search CrossRef (150M+ DOI records)."""
        if not _AIOHTTP_AVAILABLE:
            return []

        url = "https://api.crossref.org/works"
        params = {
            "query": query,
            "rows": 10,
            "select": "DOI,title,author,published-print,is-referenced-by-count,abstract",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers={"User-Agent": "DarkLab/1.0 (mailto:steve@opensens.io)"},
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    items = data.get("message", {}).get("items", [])

                    results: list[SearchResult] = []
                    for item in items:
                        title_list = item.get("title", [])
                        title = title_list[0] if title_list else ""
                        authors = [
                            f"{a.get('given', '')} {a.get('family', '')}".strip()
                            for a in (item.get("author") or [])
                        ]
                        pub = item.get("published-print", {}).get("date-parts", [[None]])
                        year = pub[0][0] if pub and pub[0] else None

                        results.append(SearchResult(
                            title=title,
                            authors=authors[:5],
                            abstract=(item.get("abstract", "") or "")[:500],
                            url=f"https://doi.org/{item.get('DOI', '')}",
                            doi=item.get("DOI", ""),
                            source="crossref",
                            year=year,
                            citation_count=item.get("is-referenced-by-count", 0),
                            is_peer_reviewed=True,
                        ))
                    return results
        except Exception as exc:
            logger.warning("crossref_search_failed: %s", exc)
            return []

    async def search_europepmc(self, query: str) -> list[SearchResult]:
        """Search Europe PMC (PubMed + PMC + preprints)."""
        if not _AIOHTTP_AVAILABLE:
            return []

        encoded = urllib.parse.quote(query)
        url = (
            f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
            f"query={encoded}&resultType=core&pageSize=10&format=json"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    entries = data.get("resultList", {}).get("result", [])

                    results: list[SearchResult] = []
                    for e in entries:
                        authors_str = e.get("authorString", "")
                        authors = [a.strip() for a in authors_str.split(",")][:5] if authors_str else []
                        year_str = e.get("pubYear")
                        year = int(year_str) if year_str and year_str.isdigit() else None

                        results.append(SearchResult(
                            title=e.get("title", ""),
                            authors=authors,
                            abstract=(e.get("abstractText", "") or "")[:500],
                            url=f"https://europepmc.org/article/{e.get('source', 'MED')}/{e.get('id', '')}",
                            doi=e.get("doi", "") or "",
                            source="europepmc",
                            year=year,
                            citation_count=e.get("citedByCount", 0),
                            is_peer_reviewed=e.get("inEPMC") == "Y",
                        ))
                    return results
        except Exception as exc:
            logger.warning("europepmc_search_failed: %s", exc)
            return []
