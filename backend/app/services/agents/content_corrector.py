"""Content Corrector Agent – minimal final-pass correction for teaching replies."""

from __future__ import annotations

from app.services.agents.base_agent import BaseAgent


class ContentCorrectorAgent(BaseAgent):
    """Audit a completed reply and only rewrite defects that must be fixed."""

    config_file = "content_corrector"
