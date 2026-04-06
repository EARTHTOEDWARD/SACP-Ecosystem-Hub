from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal


ErrorKind = Literal["transient", "contract", "infra"]


@dataclass(frozen=True)
class AdapterCapability:
    name: str
    adapter_type: Literal["api", "cli", "python"]
    entrypoints: Dict[str, str]
    produced_artifact_types: List[str] = field(default_factory=list)
    required_artifact_types: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PreparedCall:
    adapter_name: str
    action: str
    payload: Dict[str, Any]


@dataclass(frozen=True)
class AdapterResult:
    ok: bool
    payload: Dict[str, Any] = field(default_factory=dict)
    error_kind: ErrorKind | None = None
    error_message: str | None = None
    raw_stdout: str = ""
    raw_stderr: str = ""


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    errors: List[str] = field(default_factory=list)


class Adapter(ABC):
    @abstractmethod
    def capabilities(self) -> AdapterCapability:
        raise NotImplementedError

    @abstractmethod
    def prepare(self, stage_input_refs: Dict[str, Any]) -> PreparedCall:
        raise NotImplementedError

    @abstractmethod
    def execute(self, prepared_call: PreparedCall) -> AdapterResult:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, adapter_result: AdapterResult) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def validate(self, normalized_artifacts: List[Dict[str, Any]]) -> ValidationReport:
        raise NotImplementedError
