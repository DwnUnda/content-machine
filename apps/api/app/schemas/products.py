from pydantic import BaseModel, Field

from app.schemas.common import TimestampedResponse


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    brand: str | None = None
    category: str | None = None
    role: str | None = None
    product_url: str | None = None
    personally_tested: bool = False
    model_number: str | None = None
    retailer_domain: str | None = None
    price_text: str | None = None
    capacity_text: str | None = None
    tank_size_text: str | None = None
    noise_level_text: str | None = None
    power_use_text: str | None = None
    warranty_text: str | None = None
    drainage_text: str | None = None
    room_size_text: str | None = None
    review_rating_text: str | None = None
    review_count_text: str | None = None
    description_snippet: str | None = None
    visible_specs_table: dict | None = None
    confidence_level: str | None = None
    confidence_score: int | None = None
    common_positives: str | None = None
    common_complaints: str | None = None
    who_should_buy: str | None = None
    who_should_avoid: str | None = None
    best_for: str | None = None
    bottom_line: str | None = None
    extraction_status: str | None = None
    extraction_error: str | None = None
    raw_extracted_json: dict | None = None
    notes: str | None = None
    # Review-led product analysis layer (additive, all optional).
    manufacturer_url: str | None = None
    retailer_urls: list | None = None
    positive_review_patterns: str | None = None
    negative_review_patterns: str | None = None
    reliability_concerns: str | None = None
    key_specs: list | None = None
    price_range_text: str | None = None
    australian_availability: str | None = None
    review_methodology_notes: str | None = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = None
    brand: str | None = None
    category: str | None = None
    role: str | None = None
    product_url: str | None = None
    personally_tested: bool | None = None
    model_number: str | None = None
    retailer_domain: str | None = None
    price_text: str | None = None
    capacity_text: str | None = None
    tank_size_text: str | None = None
    noise_level_text: str | None = None
    power_use_text: str | None = None
    warranty_text: str | None = None
    drainage_text: str | None = None
    room_size_text: str | None = None
    review_rating_text: str | None = None
    review_count_text: str | None = None
    description_snippet: str | None = None
    visible_specs_table: dict | None = None
    confidence_level: str | None = None
    confidence_score: int | None = None
    common_positives: str | None = None
    common_complaints: str | None = None
    who_should_buy: str | None = None
    who_should_avoid: str | None = None
    best_for: str | None = None
    bottom_line: str | None = None
    extraction_status: str | None = None
    extraction_error: str | None = None
    raw_extracted_json: dict | None = None
    notes: str | None = None
    # Review-led product analysis layer (additive, all optional).
    manufacturer_url: str | None = None
    retailer_urls: list | None = None
    positive_review_patterns: str | None = None
    negative_review_patterns: str | None = None
    reliability_concerns: str | None = None
    key_specs: list | None = None
    price_range_text: str | None = None
    australian_availability: str | None = None
    review_methodology_notes: str | None = None


class ProductResponse(TimestampedResponse):
    name: str
    brand: str | None = None
    category: str | None = None
    role: str | None = None
    product_url: str | None = None
    personally_tested: bool
    model_number: str | None = None
    retailer_domain: str | None = None
    price_text: str | None = None
    capacity_text: str | None = None
    tank_size_text: str | None = None
    noise_level_text: str | None = None
    power_use_text: str | None = None
    warranty_text: str | None = None
    drainage_text: str | None = None
    room_size_text: str | None = None
    review_rating_text: str | None = None
    review_count_text: str | None = None
    description_snippet: str | None = None
    visible_specs_table: dict | None = None
    confidence_level: str | None = None
    confidence_score: int | None = None
    common_positives: str | None = None
    common_complaints: str | None = None
    who_should_buy: str | None = None
    who_should_avoid: str | None = None
    best_for: str | None = None
    bottom_line: str | None = None
    extraction_status: str | None = None
    extraction_error: str | None = None
    raw_extracted_json: dict | None = None
    notes: str | None = None
    # Review-led product analysis layer (additive, all optional).
    manufacturer_url: str | None = None
    retailer_urls: list | None = None
    positive_review_patterns: str | None = None
    negative_review_patterns: str | None = None
    reliability_concerns: str | None = None
    key_specs: list | None = None
    price_range_text: str | None = None
    australian_availability: str | None = None
    review_methodology_notes: str | None = None
