"""Answer format of the vision tool: what the model must fill in for each image.

The model does not answer with free text: it fills in this fixed form and
Pydantic checks it. Rule: the model only reports what it SEES. Anything that
must be exact (which file it was, whether its text looks like a prompt
injection) is added later by our own code, never by the model.

Outside this module the crew still receives text (see to_text in a later step).
"""

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

MAX_OBSERVATIONS = 8  # keeps answers short and token use under control
# A long menu can have more: the first ones are kept and the rest are dropped,
# so a long menu never makes the whole analysis fail.
MAX_PRICES = 40


class ImageKind(StrEnum):
    """What the image is."""

    PHOTO = "photo"  # a photo of a venue (inside, outside, menu...)
    CHART = "chart"  # a chart made by the Analyst


class Category(StrEnum):
    """What an observation is about. Valid for any local business."""

    AMBIANCE = "ambiance"  # atmosphere and decoration
    PRICES = "prices"  # prices and menus that can be read
    OFFER = "offer"  # what they sell or which services they offer
    WORKSPACE = "workspace"  # room to work: big tables, sockets, wifi signs
    CAPACITY = "capacity"  # size, approximate number of tables or seats
    EXTERIOR = "exterior"  # front, shop window, terrace, access from the street
    OTHER = "other"  # anything else that is useful


class Confidence(StrEnum):
    """How sure the model is. Three levels: easier to read than a number."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ImageObservation(BaseModel):
    """One thing seen in the image."""

    category: Category
    observation: str = Field(
        min_length=3,
        max_length=300,
        description="One sentence in Spanish, only about what can be seen",
        examples=["Iluminación cálida con bombillas colgantes y pared de ladrillo visto"],
    )
    confidence: Confidence

class PriceItem(BaseModel):
    """One price that can be read in the image (a menu, a board, a price list)."""

    item: str = Field(
        min_length=1,
        max_length=80,
        description="Product or service, written as in the image",
        examples=["Café con leche"],
    )
    size: str | None = Field(
        default=None,
        max_length=40,
        description="Size or variant, only if the image says it (pequeño, grande, día...)",
        examples=["grande"],
    )
    price_eur: float = Field(
        gt=0, le=10_000, description="Price in euros, as a number", examples=[1.8]
    )

class ImageAnswer(BaseModel):
    """What the MODEL fills in for one image. Nothing here is decided by our code."""

    kind: ImageKind
    observations: list[ImageObservation] = Field(default_factory=list, max_length=MAX_OBSERVATIONS)
    visible_text: list[str] = Field(
        default_factory=list,
        description="Text that can be read in the image, copied exactly as it is",
        examples=[["Spoiler Bar", "Café con leche 1,80 €"]],
    )
    prices: list[PriceItem] = Field(
        default_factory=list,
        description="Every price that can be read, one per product and size",
    )
    people_visible: bool = Field(
        description="True if a person can be recognised. People are never described"
    )
    unclear: str | None = Field(
        default=None,
        description="Why nothing can be said about the image (blurred, too dark...)",
    )
    
    @field_validator("prices", mode="before")
    @classmethod
    def keep_the_first_prices(cls, value: object) -> object:
        """Keep the first MAX_PRICES prices of a long menu instead of failing."""
        return value[:MAX_PRICES] if isinstance(value, list) else value


class ImageAnalysis(ImageAnswer):
    """The model's answer plus what OUR code adds: the file and the safety check."""

    image_path: str = Field(description="The analysed file, relative to outputs/")
    suspicious: bool = Field(
        default=False, description="Its visible text was flagged by guardrails.process()"
    )
    injection_patterns: list[str] = Field(default_factory=list)