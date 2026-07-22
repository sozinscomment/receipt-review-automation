# LOGIC HEADER
# Input:          A validated Config.
# Transformation: Select and construct the extraction engine the config asks for.
#                 This is the single place that knows about all engines, so adding a
#                 new one later means one line here — no caller changes.
# Output:         An Extractor instance ready to use.

from __future__ import annotations

from extractor.config import Config
from extractor.engines.ai_engine import AIExtractor
from extractor.engines.ai_vision import AIVisionExtractor
from extractor.engines.base import Extractor
from extractor.engines.rule_based import RuleBasedExtractor


def build_engine(config: Config) -> Extractor:
    if config.engine == "rule_based":
        return RuleBasedExtractor(currency_symbols=config.currency_symbols,
                                  date_dayfirst=config.date_dayfirst)
    if config.engine == "ai":
        return AIExtractor(provider=config.ai_provider,
                           api_key=config.ai_api_key,
                           model=config.ai_model)
    if config.engine == "ai_vision":
        return AIVisionExtractor(api_key=config.ai_api_key,
                                 model=config.ai_model,
                                 config=config)
    raise ValueError(f"unknown engine: {config.engine}")
