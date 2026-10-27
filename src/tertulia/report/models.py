from datetime import date
from typing import Literal

from pydantic import BaseModel

Signal = Literal["green", "yellow", "red"]


class AgentMessage(BaseModel):
    agent: str
    name: str
    role: str
    message: str


class Verdict(BaseModel):
    signal: Signal
    label: str
    confidence: int          # 0–100
    reasons: list[str]


class ReportBrief(BaseModel):
    sector: str
    neighborhood: str
    budget_eur: float | None = None
    area_m2: float | None = None
    context: str | None = None
    profile: str = "analyst"


class ReportData(BaseModel):
    brief: ReportBrief
    debate: list[AgentMessage]
    verdict: Verdict
    generated_on: date = date.today()
    job_id: str = "N/A"
    simulated: bool = False
    tokens_used: int = 0
