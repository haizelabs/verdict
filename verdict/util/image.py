import base64
import mimetypes
from pathlib import Path
from typing import Optional, Union

from pydantic import BaseModel, Field, field_validator


class ImageModel(BaseModel):
    type: str = Field(..., description="MIME type, e.g. image/jpeg/etc.")
    data: str = Field(..., description="Base64-encoded image data")

    @field_validator("type")
    def validate_type(cls, v):
        # See https://platform.openai.com/docs/guides/images-vision#image-input-requirements
        allowed = {"image/png", "image/jpeg", "image/webp", "image/gif"}
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


def Image(
    file: Optional[Union[Path, str]] = None,
    mime: Optional[str] = None,
    blob: Optional[str] = None,
) -> ImageModel:
    """
    file: Path to the image file.

    OR

    mime: MIME type of the image.
    blob: base64-encoded image data.
    """

    if file is not None and (mime is not None or blob is not None):
        raise ValueError("Only one of file or mime/blob can be provided")

    if file is not None:
        if isinstance(file, str):
            file = Path(file)

        # See https://platform.openai.com/docs/guides/images-vision#image-input-requirements
        mime_type, _ = mimetypes.guess_type(file)
        if mime_type not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
            raise ValueError(f"Unsupported image format: {mime_type}")

        return ImageModel(
            type=mime_type,
            data=base64.b64encode(file.read_bytes()).decode("utf-8"),
        )
    elif mime is not None and blob is not None:
        return ImageModel(
            type=mime,
            data=blob,
        )
    else:
        raise ValueError("Either file or mime/blob must be provided")
