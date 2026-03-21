#!/bin/bash
# Set up Python virtual environment with role-specific dependencies

ROLE="${1:-base}"
VENV_DIR="${DARKLAB_HOME}/venv"

echo "[python] Setting up Python environment for role: ${ROLE}..."

# Create project directory if needed
mkdir -p "${DARKLAB_HOME}/agents"

# Create pyproject.toml based on role
cat > "${DARKLAB_HOME}/pyproject.toml" << 'PYPROJECT'
[project]
name = "darklab"
version = "2.1.0"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
    "httpx>=0.27",
    "python-dotenv>=1.0",
    "structlog>=24.0",
    "PyNaCl>=1.5",
]

[project.optional-dependencies]
leader = [
    "anthropic>=0.40",
    "google-generativeai>=0.8",
    "python-docx>=1.0",
    "python-pptx>=1.0",
    "Pillow>=10.0",
    # browser-use for NotebookLM automation
    "browser-use>=0.2",
    "langchain-anthropic>=0.3",
    "playwright>=1.40",
]
academic = [
    "anthropic>=0.40",
    "openai>=1.50",
    "google-generativeai>=0.8",
    "python-telegram-bot>=21",
    # browser-use for LLM-driven browser automation
    "browser-use>=0.2",
    "langchain-anthropic>=0.3",
    "langchain-openai>=0.3",
    "playwright>=1.40",
    # Research tools
    "beautifulsoup4>=4.12",
    "arxiv>=2.1",
]
experiment = [
    "anthropic>=0.40",
    "numpy>=1.26",
    "scipy>=1.12",
    "pandas>=2.2",
    "matplotlib>=3.8",
    "plotly>=5.18",
    "scikit-learn>=1.4",
    # AutoResearch: PyTorch with MPS support
    "torch>=2.2",
]
scientific = [
    # Optional: heavy deps for claude-scientific-skills scripts
    "biopython>=1.83",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.uv]
dev-dependencies = ["pytest>=8.0", "pytest-asyncio>=0.24", "ruff>=0.8"]

[tool.ruff]
line-length = 100
target-version = "py311"
PYPROJECT

# Verify uv is installed
if ! command -v uv &>/dev/null; then
    echo "ERROR: uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Install with role-specific extras
echo "[python] Installing dependencies for ${ROLE}..."
cd "${DARKLAB_HOME}"
uv sync --extra "${ROLE}"

# Post-install: install Playwright browsers for roles that use browser-use
if [[ "${ROLE}" == "leader" ]] || [[ "${ROLE}" == "academic" ]]; then
    echo "[python] Installing Playwright browsers for browser-use..."
    uv run playwright install chromium 2>/dev/null || echo "[python] Playwright browser install skipped (run manually: playwright install chromium)"
fi

echo "[python] Python environment ready at ${DARKLAB_HOME}"
