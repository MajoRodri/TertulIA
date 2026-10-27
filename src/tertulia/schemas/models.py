"""Shared data contracts for TertulIA.

Every module exchanges data using these models, so they must be agreed by the
whole team and changed only through a PR that everyone knows about.

Flow: BusinessBrief (the request) -> Sources (where data comes from)
-> Findings (each figure, traceable to a source or to code) -> Verdict.
Every tool call is recorded as a TraceEntry, so a third party can audit
which agent did what, with which tool, on which source.

Identifiers are in English (team rule). In the UI and the report the models
are shown with their Madrid names: Km. 0, La Portera, Chulapo Analytics, ¿Mola?
"""

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    computed_field,
    field_validator,
    model_validator,
)


class UserProfile(StrEnum):
    """Who is using TertulIA."""

    ANALYST = "analyst"  # consultancy analyst (main user)
    ENTREPRENEUR = "entrepreneur"  # first orientation, may be referred to a consultancy


class SourceType(StrEnum):
    """Where a piece of data comes from."""

    API = "api"  # Google Places, Foursquare...
    OPEN_DATA = "open_data"  # Madrid City Council, INE, OpenStreetMap
    WEB = "web"  # a competitor's website read with fetch
    IMAGE = "image"  # a photo or chart analysed by the vision agent
    USER_INPUT = "user_input"  # typed in by the user (known rent, business mix...)


class FindingStatus(StrEnum):
    """Whether a finding has a value or the data could not be found."""

    OK = "ok"
    MISSING = "missing"  # "sin dato": never invented, left for the human to fill in


class TrafficLight(StrEnum):
    """Final recommendation."""

    GREEN = "green"
    AMBER = "amber"
    RED = "red"


# Photos the user can upload for the vision agent: images only, for now.
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")
MAX_IMAGES = 10


class BusinessBrief(BaseModel):
    """The request: what business, where, and for whom. UI name: "Km. 0"."""

    business_type: str = Field(
        description="Sector profile name, must match a file in config/sectores/",
        examples=["cafe_cowork"],
    )
    neighbourhood: str = Field(min_length=2, examples=["Atocha"])
    city: str = "Madrid"
    budget_eur: float | None = Field(default=None, gt=0, description="Initial budget")
    known_rent_eur: float | None = Field(
        default=None, gt=0, description="Monthly rent if the user already has a venue"
    )
    area_m2: float | None = Field(default=None, gt=0, description="Business space in square metres")
    radius_m: int = Field(default=800, ge=100, description="Search radius in metres")
    user_profile: UserProfile = UserProfile.ANALYST
    notes: str = Field(default="", description="Free text, anonymised before use")
    image_paths: list[str] = Field(
        default_factory=list,
        max_length=MAX_IMAGES,
        description="Photos uploaded by the user for the vision agent, relative to outputs/",
        examples=[["run-001/uploads/competitor_front.jpg"]],
    )

    @field_validator("image_paths")
    @classmethod
    def image_paths_are_safe(cls, paths: list[str]) -> list[str]:
        """Only jpg/png files, given as paths relative to outputs/.

        "photo.jpg" means outputs/photo.jpg and "run-001/uploads/a.png" means
        outputs/run-001/uploads/a.png. A path that could point outside outputs/
        is refused: one with "..", an absolute one or a Windows drive. The
        vision agent will open these files, so "../.env" must never get through.

        This is the first check, on the text of the path. The vision module
        checks again when it opens each file: it resolves the real path and
        confirms it is still inside the allowed folder (links included).
        """
        for path in paths:
            parts = PurePosixPath(path.replace("\\", "/"))
            if parts.is_absolute() or ".." in parts.parts or ":" in path:
                raise ValueError(f"image path must be relative to outputs/: {path!r}")
            if parts.suffix.lower() not in IMAGE_EXTENSIONS:
                raise ValueError(f"only jpg and png images are accepted: {path!r}")
        return paths


class Source(BaseModel):
    """Where data was obtained. UI name: "La Portera".

    A suspicious source is kept (traceability) but never used for a finding,
    and it is listed as a warning in the verdict.
    """

    id: str = Field(pattern=r"^src-\d{3,}$", examples=["src-001"])
    source_type: SourceType
    title: str
    url: str | None = Field(default=None, description="Required except for user input")
    retrieved_at: AwareDatetime = Field(
        description="When it was really read (for cached data: the capture date)"
    )
    retrieved_by: str = Field(
        description="Tool that got it", examples=["mcp.osm_search"]
    )
    from_cache: bool = Field(
        default=False,
        description="True if it comes from saved demo data, not a live call",
    )
    suspicious: bool = Field(
        default=False, description="Flagged by guardrails.process()"
    )
    injection_patterns: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def url_required_for_external_sources(self) -> "Source":
        if self.source_type != SourceType.USER_INPUT and not self.url:
            raise ValueError("external sources must have a url")
        return self


class Finding(BaseModel):
    """One fact or figure used in the report. UI name: "Chulapo Analytics".

    One figure per finding: a tool that returns several figures produces
    several findings, each with its own unit.
    """

    id: str = Field(pattern=r"^fnd-\d{3,}$", examples=["fnd-001"])
    claim: str = Field(
        description="The fact, in Spanish, as it will read in the report"
    )
    value: float | str | None = None
    unit: str | None = Field(default=None, examples=["EUR/month", "members/month", "%"])
    status: FindingStatus = FindingStatus.OK
    source_ids: list[str] = Field(default_factory=list)
    code_ref: str | None = Field(
        default=None, description="Id of the TraceEntry that computed the value"
    )
    artifact_paths: list[str] = Field(
        default_factory=list,
        description="Charts or files, relative to outputs/",
        examples=[["run-001/charts/break_even.png"]],
    )
    agent: str = Field(examples=["researcher", "analyst", "vision"])

    @model_validator(mode="after")
    def must_be_traceable(self) -> "Finding":
        if self.status == FindingStatus.OK and not (self.source_ids or self.code_ref):
            raise ValueError("a finding needs at least one source_id or a code_ref")
        if self.status == FindingStatus.MISSING and self.value is not None:
            raise ValueError("a missing finding cannot have a value")
        return self


class Verdict(BaseModel):
    """The traffic-light recommendation. UI name: "¿Mola?".

    The system proposes `light` and computes `confidence` with a fixed formula.
    The analyst has the final word: they can override either one, but must give
    a reason. Both values are kept, so the change can be audited.
    """

    light: TrafficLight = Field(description="Proposed by the system")
    confidence: float = Field(
        ge=0, le=1, description="Computed by the graph, never edited"
    )
    summary: str
    reasons: list[str] = Field(min_length=1)
    finding_ids: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(
        default_factory=list, description="E.g. suspicious sources that were discarded"
    )
    light_override: TrafficLight | None = Field(
        default=None, description="Set by the analyst"
    )
    confidence_override: float | None = Field(
        default=None, ge=0, le=1, description="Set by the analyst"
    )
    override_reason: str | None = None
    approved_by_human: bool = False

    @model_validator(mode="after")
    def override_needs_reason(self) -> "Verdict":
        overridden = (
            self.light_override is not None or self.confidence_override is not None
        )
        if overridden and not (self.override_reason and self.override_reason.strip()):
            raise ValueError("an override needs a reason")
        return self

    @computed_field
    @property
    def final_light(self) -> TrafficLight:
        """The analyst's light if they changed it, otherwise the system's."""
        return self.light_override or self.light

    @computed_field
    @property
    def final_confidence(self) -> float:
        """The analyst's confidence if they changed it, otherwise the system's."""
        if self.confidence_override is not None:
            return self.confidence_override
        return self.confidence


class TraceEntry(BaseModel):
    """One line of the audit log: who did what, with which tool, on which data.

    Everything is stored (inputs, code and output) so any figure can be
    reproduced. Human actions (approve, override) are logged the same way.
    """

    id: str = Field(pattern=r"^trc-\d{3,}$", examples=["trc-001"])
    timestamp: AwareDatetime
    actor: str = Field(examples=["researcher", "analyst", "vision", "human"])
    tool: str = Field(examples=["code_exec", "mcp.osm_search", "ui.override"])
    inputs: dict[str, Any] = Field(default_factory=dict)
    code: str | None = Field(default=None, description="Full script, if code was run")
    output: Any = None
    source_ids: list[str] = Field(default_factory=list)
    finding_ids: list[str] = Field(default_factory=list)
    tokens_used: int = Field(default=0, ge=0)
    error: str | None = None


def compute_confidence(
    findings: list[Finding],
    sources: list[Source],
    missing_penalty: float = 0.1,
    suspicious_penalty: float = 0.05,
) -> float:
    """Fixed, reproducible confidence formula.

    Starts at 1 and subtracts a penalty for each missing finding and each
    suspicious source. The penalties are passed in from config/settings.py.
    """
    missing = sum(f.status == FindingStatus.MISSING for f in findings)
    suspicious = sum(s.suspicious for s in sources)
    score = 1 - missing * missing_penalty - suspicious * suspicious_penalty
    return round(max(0.0, min(1.0, score)), 2)
