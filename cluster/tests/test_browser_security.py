"""Tests for browser agent domain allowlist and security features."""
import pytest
from unittest.mock import patch


class TestCheckDomainAllowed:
    """Tests for the domain allowlist enforcement."""

    def _check(self, url: str, allowlist: str = "") -> bool:
        """Helper that patches settings and calls check_domain_allowed."""
        with patch("academic.browser_agent.settings") as mock_settings:
            allowed_set = {d.strip().lower() for d in allowlist.split(",") if d.strip()}
            mock_settings.browser_domain_allowlist = allowed_set
            from academic.browser_agent import check_domain_allowed
            return check_domain_allowed(url)

    def test_allowed_exact_match(self):
        assert self._check("https://perplexity.ai/search", "perplexity.ai,google.com")

    def test_allowed_subdomain(self):
        assert self._check("https://scholar.google.com/scholar", "google.com,arxiv.org")

    def test_blocked_domain(self):
        assert not self._check("https://evil.com/hack", "perplexity.ai,google.com")

    def test_empty_allowlist_permits_all(self):
        assert self._check("https://anything.com", "")

    def test_no_scheme(self):
        assert self._check("perplexity.ai/search", "perplexity.ai")

    def test_invalid_url_blocked(self):
        assert not self._check("", "perplexity.ai")

    def test_deep_subdomain(self):
        assert self._check("https://a.b.c.google.com/path", "google.com")

    def test_partial_match_blocked(self):
        """google.com.evil.com should NOT match allowlist 'google.com'."""
        assert not self._check("https://google.com.evil.com", "google.com")

    def test_case_insensitive(self):
        assert self._check("https://PERPLEXITY.AI/search", "perplexity.ai")

    def test_arxiv(self):
        assert self._check("https://arxiv.org/abs/2301.00001", "arxiv.org")

    def test_pubmed(self):
        assert self._check(
            "https://pubmed.ncbi.nlm.nih.gov/12345",
            "pubmed.ncbi.nlm.nih.gov,google.com",
        )

    def test_biorxiv(self):
        assert self._check("https://www.biorxiv.org/content/123", "biorxiv.org")


class TestDomainBlockedError:
    """Tests for the DomainBlockedError exception."""

    def test_error_is_exception(self):
        from academic.browser_agent import DomainBlockedError
        err = DomainBlockedError("test.com blocked")
        assert isinstance(err, Exception)
        assert "test.com" in str(err)


class TestMakeTaskProfile:
    """Tests for per-task browser profile isolation."""

    def test_creates_unique_dirs(self):
        from academic.browser_agent import _make_task_profile
        dir1 = _make_task_profile("test")
        dir2 = _make_task_profile("test")
        assert dir1 != dir2
        assert dir1.exists()
        assert dir2.exists()
        # Cleanup
        dir1.rmdir()
        dir2.rmdir()

    def test_dir_name_includes_task(self):
        from academic.browser_agent import _make_task_profile
        d = _make_task_profile("perplexity")
        assert "perplexity" in d.name
        d.rmdir()
