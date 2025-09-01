from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class AutomationRule:
    pattern: str
    response: str
    name: Optional[str] = None
    once: bool = True
    case_sensitive: bool = False
    delay_ms: int = 0
    is_active: bool = True

    # runtime state
    _fired: bool = False

    def matches(self, text: str) -> bool:
        if not self.is_active:
            return False
        if self.once and self._fired:
            return False
        flags = 0 if self.case_sensitive else re.IGNORECASE
        return re.search(self.pattern, text, flags) is not None

    def mark_fired(self) -> None:
        self._fired = True


class AutomationEngine:
    def __init__(self, rules: List[AutomationRule] | None = None) -> None:
        self.rules: List[AutomationRule] = rules or []

    def evaluate(self, chunk: str) -> Optional[str]:
        """
        Evaluate incoming output text against rules in order.
        Returns the first response to send, or None.
        """
        for rule in self.rules:
            if rule.matches(chunk):
                rule.mark_fired()
                return rule.response
        return None
