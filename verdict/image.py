import base64

from pydantic import BaseModel, Field, field_validator


class Image(BaseModel):
    type: str = Field(..., description="MIME type, e.g. image/jpeg/etc.")
    data: str = Field(..., description="Base64-encoded image data")

    @field_validator("type")
    def validate_type(cls, v):
        # See https://platform.openai.com/docs/guides/images-vision#image-input-requirements
        allowed = {"image/jpeg", "image/png", "image/gif", "image/webp"}
        if v not in allowed:
            raise ValueError(f"Unsupported image MIME type: {v}")
        return v

    @field_validator("data")
    def validate_base64(cls, v):
        try:
            base64.b64decode(v, validate=True)
        except Exception:
            raise ValueError("Invalid base64 data")
        return v
