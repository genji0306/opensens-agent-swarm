"""Shared fixtures for oas_core tests."""
import pytest


@pytest.fixture
def company_id():
    return "comp_test123"


@pytest.fixture
def agent_id():
    return "agent_test456"
