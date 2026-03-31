"""Settings loader from ~/.darklab/.env."""
from __future__ import annotations

__all__ = ["Settings", "get_settings", "settings"]

import os
from pathlib import Path
from functools import lru_cache

from pydantic import BaseModel, Field

# Load .env before anything else
try:
    from dotenv import load_dotenv
    load_dotenv(Path.home() / ".darklab" / ".env")
except ImportError:
    pass


class Settings(BaseModel):
    # Role
    darklab_role: str = Field(default_factory=lambda: os.getenv("DARKLAB_ROLE", "unknown"))

    # API Keys
    anthropic_api_key: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    google_ai_api_key: str = Field(default_factory=lambda: os.getenv("GOOGLE_AI_API_KEY", ""))
    perplexity_api_key: str = Field(default_factory=lambda: os.getenv("PERPLEXITY_API_KEY", ""))

    # Telegram
    telegram_bot_token: str = Field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))

    # Networking
    leader_host: str = Field(default_factory=lambda: os.getenv("DARKLAB_LEADER_HOST", "leader.local"))
    leader_port: int = Field(default_factory=lambda: int(os.getenv("DARKLAB_LEADER_PORT", "18789")))
    gateway_port: int = Field(default_factory=lambda: int(os.getenv("GATEWAY_PORT", "18789")))

    # Paperclip
    paperclip_url: str = Field(default_factory=lambda: os.getenv("PAPERCLIP_URL", ""))
    paperclip_api_key: str = Field(default_factory=lambda: os.getenv("PAPERCLIP_API_KEY", ""))
    paperclip_company_id: str = Field(default_factory=lambda: os.getenv("PAPERCLIP_COMPANY_ID", ""))
    paperclip_agent_id: str = Field(default_factory=lambda: os.getenv("PAPERCLIP_AGENT_ID", ""))

    # OpenViking (memory)
    openviking_url: str = Field(default_factory=lambda: os.getenv("OPENVIKING_URL", ""))
    openviking_api_key: str = Field(default_factory=lambda: os.getenv("OPENVIKING_API_KEY", ""))

    # Redis
    redis_url: str = Field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379"))

    # LiteLLM proxy (when set, LLM calls route through this instead of direct APIs)
    litellm_base_url: str = Field(default_factory=lambda: os.getenv("LITELLM_BASE_URL", ""))

    # AIClient-2-API (boost tier — free client accounts, optional fallback)
    aiclient_base_url: str = Field(default_factory=lambda: os.getenv("AICLIENT_BASE_URL", ""))
    aiclient_api_key: str = Field(default_factory=lambda: os.getenv("AICLIENT_API_KEY", "darklab-internal"))
    boost_enabled: bool = Field(default_factory=lambda: os.getenv("DARKLAB_BOOST_ENABLED", "").lower() in ("true", "1", "yes"))
    boost_daily_limit: int = Field(default_factory=lambda: int(os.getenv("DARKLAB_BOOST_DAILY_LIMIT", "100")))

    # RL (OpenClaw-RL + MiroShark)
    rl_enabled: bool = Field(default_factory=lambda: os.getenv("DARKLAB_RL_ENABLED", "").lower() in ("true", "1", "yes"))
    rl_enabled_agents: str = Field(default_factory=lambda: os.getenv("DARKLAB_RL_ENABLED_AGENTS", ""))
    rl_proxy_url: str = Field(default_factory=lambda: os.getenv("DARKLAB_RL_PROXY_URL", ""))
    rl_training_method: str = Field(default_factory=lambda: os.getenv("DARKLAB_RL_TRAINING_METHOD", "combine"))
    rl_batch_size: int = Field(default_factory=lambda: int(os.getenv("DARKLAB_RL_BATCH_SIZE", "16")))
    rl_lora_rank: int = Field(default_factory=lambda: int(os.getenv("DARKLAB_RL_LORA_RANK", "32")))
    rl_min_promotion_score: float = Field(default_factory=lambda: float(os.getenv("DARKLAB_RL_MIN_PROMOTION_SCORE", "0.7")))
    rl_daily_budget: float = Field(default_factory=lambda: float(os.getenv("DARKLAB_RL_DAILY_BUDGET", "10.0")))
    tinker_api_key: str = Field(default_factory=lambda: os.getenv("DARKLAB_TINKER_API_KEY", ""))
    miroshark_url: str = Field(default_factory=lambda: os.getenv("DARKLAB_MIROSHARK_URL", ""))
    miroshark_enabled: bool = Field(default_factory=lambda: os.getenv("DARKLAB_MIROSHARK_ENABLED", "").lower() in ("true", "1", "yes"))
    debate_default_rounds: int = Field(default_factory=lambda: int(os.getenv("DARKLAB_DEBATE_DEFAULT_ROUNDS", "10")))
    debate_default_agents: int = Field(default_factory=lambda: int(os.getenv("DARKLAB_DEBATE_DEFAULT_AGENTS", "15")))

    # TurboQuant KV cache compression
    turbo_quant_enabled: bool = Field(default_factory=lambda: os.getenv("DARKLAB_TURBOQUANT_ENABLED", "").lower() in ("true", "1", "yes"))
    turbo_quant_bits: int = Field(default_factory=lambda: int(os.getenv("DARKLAB_TURBOQUANT_BITS", "4")))
    turbo_quant_pool_mb: int = Field(default_factory=lambda: int(os.getenv("DARKLAB_TURBOQUANT_POOL_MB", "4096")))
    turbo_quant_enable_qjl: bool = Field(default_factory=lambda: os.getenv("DARKLAB_TURBOQUANT_QJL", "true").lower() in ("true", "1", "yes"))
    turbo_quant_middle_out: bool = Field(default_factory=lambda: os.getenv("DARKLAB_TURBOQUANT_MIDDLE_OUT", "").lower() in ("true", "1", "yes"))

    # Browser security
    browser_allowed_domains: str = Field(
        default_factory=lambda: os.getenv(
            "DARKLAB_BROWSER_ALLOWED_DOMAINS",
            "perplexity.ai,scholar.google.com,arxiv.org,pubmed.ncbi.nlm.nih.gov,semanticscholar.org,google.com,biorxiv.org,medrxiv.org",
        )
    )
    browser_max_steps: int = Field(default_factory=lambda: int(os.getenv("DARKLAB_BROWSER_MAX_STEPS", "20")))
    browser_headless: bool = Field(
        default_factory=lambda: os.getenv("DARKLAB_BROWSER_HEADLESS", "true").lower() in ("true", "1", "yes")
    )

    # Node addresses for HTTP dispatch (leader → academic/experiment)
    academic_host: str = Field(default_factory=lambda: os.getenv("DARKLAB_ACADEMIC_HOST", ""))
    academic_port: int = Field(default_factory=lambda: int(os.getenv("DARKLAB_ACADEMIC_PORT", "8200")))
    experiment_host: str = Field(default_factory=lambda: os.getenv("DARKLAB_EXPERIMENT_HOST", ""))
    experiment_port: int = Field(default_factory=lambda: int(os.getenv("DARKLAB_EXPERIMENT_PORT", "8300")))

    # Paths
    darklab_home: Path = Field(default_factory=lambda: Path(os.getenv("DARKLAB_HOME", str(Path.home() / ".darklab"))))
    signing_key_path: Path = Field(default_factory=lambda: Path(os.getenv(
        "SIGNING_PRIVATE_KEY_PATH",
        str(Path.home() / ".darklab" / "keys" / "signing.key"),
    )))
    signing_pub_path: Path = Field(default_factory=lambda: Path(os.getenv(
        "SIGNING_PUBLIC_KEY_PATH",
        str(Path.home() / ".darklab" / "keys" / "signing.pub"),
    )))

    # Logging
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    @property
    def rl_enabled_agent_set(self) -> set[str]:
        """Parsed set of RL-enabled agent names."""
        return {a.strip().lower() for a in self.rl_enabled_agents.split(",") if a.strip()}

    @property
    def rl_dir(self) -> Path:
        d = self.darklab_home / "rl"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def rl_rollouts_dir(self) -> Path:
        d = self.rl_dir / "rollouts"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def rl_checkpoints_dir(self) -> Path:
        d = self.rl_dir / "checkpoints"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def rl_baselines_dir(self) -> Path:
        d = self.rl_dir / "baselines"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def rl_evaluations_dir(self) -> Path:
        d = self.rl_dir / "evaluations"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def browser_domain_allowlist(self) -> set[str]:
        """Parsed set of allowed browser domains."""
        return {d.strip().lower() for d in self.browser_allowed_domains.split(",") if d.strip()}

    @property
    def artifacts_dir(self) -> Path:
        d = self.darklab_home / "artifacts"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def logs_dir(self) -> Path:
        d = self.darklab_home / "logs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def data_dir(self) -> Path:
        d = self.darklab_home / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
