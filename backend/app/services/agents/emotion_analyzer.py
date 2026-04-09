"""Emotion Analyzer Agent – student emotional state assessment."""

from __future__ import annotations

from typing import Any

from app.services.agents.base_agent import BaseAgent


class EmotionAnalyzerAgent(BaseAgent):
    config_file = "emotion_analyzer"
