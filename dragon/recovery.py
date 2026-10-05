"""Error classification and finite recovery policy for DRAGON V5."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from dragon.config import load_mapping


class ErrorCategory(str, Enum):
    TRANSIENT = "TRANSIENT"
    DEPENDENCY = "DEPENDENCY"
    CONTENT = "CONTENT"
    VALIDATION = "VALIDATION"
    ENVIRONMENT = "ENVIRONMENT"
    CODE_DEFECT = "CODE_DEFECT"
    DELIVERY = "DELIVERY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RecoveryDecision:
    category: ErrorCategory
    action: str
    delay_seconds: float
    attempt: int
    max_attempts: int
    reason: str


class ErrorClassifier:
    def __init__(self, code_categories: dict[str, str] | None = None):
        self.code_categories = code_categories or {}

    def classify(self, code: str, exception: BaseException | None = None) -> ErrorCategory:
        configured = self.code_categories.get(code)
        if configured:
            return ErrorCategory(configured)
        if isinstance(exception, (TimeoutError, ConnectionError)):
            return ErrorCategory.TRANSIENT
        prefixes = {
            "SOURCE_": ErrorCategory.CONTENT,
            "ARTICLE_": ErrorCategory.CONTENT,
            "PDF_": ErrorCategory.VALIDATION,
            "EPUB_": ErrorCategory.VALIDATION,
            "RTL_": ErrorCategory.VALIDATION,
            "ARABIC_": ErrorCategory.VALIDATION,
            "CONFIG_": ErrorCategory.ENVIRONMENT,
            "PREFLIGHT_": ErrorCategory.ENVIRONMENT,
            "GIT_": ErrorCategory.DELIVERY,
            "GITHUB_": ErrorCategory.DELIVERY,
            "WHATSAPP_": ErrorCategory.DELIVERY,
            "UNHANDLED_": ErrorCategory.CODE_DEFECT,
        }
        for prefix, category in prefixes.items():
            if code.startswith(prefix):
                return category
        return ErrorCategory.UNKNOWN


class RecoveryPolicy:
    def __init__(self, value: dict[str, Any]):
        if value.get("version") != 5:
            raise ValueError("RECOVERY_POLICY_VERSION_INVALID")
        defaults = value.get("defaults")
        categories = value.get("categories")
        codes = value.get("error_codes")
        if not all(isinstance(item, dict) for item in (defaults, categories, codes)):
            raise ValueError("RECOVERY_POLICY_INVALID")
        self.value = value
        self.defaults = defaults
        self.categories = categories
        self.codes = codes
        for name in ErrorCategory:
            if name.value not in categories:
                raise ValueError(f"RECOVERY_CATEGORY_MISSING:{name.value}")

    @classmethod
    def load(cls, path: Path) -> "RecoveryPolicy":
        return cls(load_mapping(path))

    @property
    def code_categories(self) -> dict[str, str]:
        return {
            code: str(rule["category"])
            for code, rule in self.codes.items()
            if isinstance(rule, dict) and "category" in rule
        }

    def rule(self, code: str, category: ErrorCategory) -> dict[str, Any]:
        combined = dict(self.defaults)
        combined.update(self.categories.get(category.value, {}))
        combined.update(self.codes.get(code, {}))
        return combined


class RecoveryEngine:
    def __init__(
        self,
        policy: RecoveryPolicy,
        *,
        sleeper: Callable[[float], None] | None = None,
    ):
        self.policy = policy
        self.classifier = ErrorClassifier(policy.code_categories)
        self.sleeper = sleeper

    def decide(self, code: str, attempt: int) -> RecoveryDecision:
        category = self.classifier.classify(code)
        rule = self.policy.rule(code, category)
        max_attempts = int(rule.get("max_attempts", 1))
        action = str(rule.get("action", "INCIDENT")).upper()
        if attempt >= max_attempts and action == "RETRY":
            action = "INCIDENT"
        initial = float(rule.get("initial_backoff_seconds", 0))
        multiplier = float(rule.get("backoff_multiplier", 2))
        maximum = float(rule.get("maximum_backoff_seconds", initial))
        delay = min(maximum, initial * (multiplier ** max(0, attempt - 1)))
        if action != "RETRY":
            delay = 0
        return RecoveryDecision(
            category=category,
            action=action,
            delay_seconds=delay,
            attempt=attempt,
            max_attempts=max_attempts,
            reason=f"{code} classified {category.value}; policy action {action}",
        )

    def wait(self, decision: RecoveryDecision) -> None:
        if decision.action == "RETRY" and decision.delay_seconds and self.sleeper:
            self.sleeper(decision.delay_seconds)
