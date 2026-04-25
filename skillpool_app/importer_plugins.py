from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List


@dataclass
class ImportCandidate:
    name: str
    source_type: str
    source_locator: str
    metadata: Dict[str, str]


class ImportPlugin(ABC):
    """Reserved interface for future openhub / skillhub importers."""

    @abstractmethod
    def search(self, query: str, **kwargs) -> List[ImportCandidate]:
        raise NotImplementedError

    @abstractmethod
    def materialize(self, candidate: ImportCandidate, destination: Path, **kwargs) -> Iterable[Path]:
        raise NotImplementedError
