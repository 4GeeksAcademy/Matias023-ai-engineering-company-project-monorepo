"""Validated classification output for TrackFlow RFP intake."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Department = Literal["warehouse", "lastmile", "reverse"]


class RFPClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_rfp: bool
    document_type: Literal["formal_rfp", "informal_rfp", "not_rfp"]
    reasoning: str = Field(min_length=1)

    client_name: str | None = None
    client_country: str | None = None
    services_requested: list[str] = Field(default_factory=list)
    monthly_volume: int | None = Field(default=None, ge=0)
    deadline: str | None = None
    budget_range: str | None = None

    departments_needed: list[Department] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_consistency(self):
        if self.is_rfp != (self.document_type != "not_rfp"):
            raise ValueError("RFP classification is inconsistent")

        if len(self.departments_needed) != len(set(self.departments_needed)):
            raise ValueError("Duplicate departments are not allowed")

        if not self.is_rfp and self.departments_needed:
            raise ValueError("Non-RFP documents cannot activate departments")

        return self
