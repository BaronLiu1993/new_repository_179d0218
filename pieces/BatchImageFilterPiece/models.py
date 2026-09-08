from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, conint


class OutputTypeEnum(str, Enum):
    file = "file"
    base64_string = "base64_string"
    both = "both"


class InputModel(BaseModel):
    """
    Batch Image Filter Piece Input Model
    """

    input_images: List[Optional[str]] = Field(
        default=[],
        description="Input images. Each item should be either a path to a file, a base64 encoded string, or null.",
        json_schema_extra={"from_upstream": "allowed"},
    )
    sepia: bool = Field(default=False, description="Apply sepia effect.")
    black_and_white: bool = Field(default=False, description="Apply black and white effect.")
    brightness: bool = Field(default=False, description="Apply brightness effect.")
    darkness: bool = Field(default=False, description="Apply darkness effect.")
    contrast: bool = Field(default=False, description="Apply contrast effect.")
    red: bool = Field(default=False, description="Apply red effect.")
    green: bool = Field(default=False, description="Apply green effect.")
    blue: bool = Field(default=False, description="Apply blue effect.")
    cool: bool = Field(default=False, description="Apply cool effect.")
    warm: bool = Field(default=False, description="Apply warm effect.")
    output_type: OutputTypeEnum = Field(
        default=OutputTypeEnum.both,
        description="Format of each output image.",
    )
    max_concurrency: conint(ge=1) = Field(
        default=8,
        description="Maximum number of images to process concurrently.",
    )


class OutputModel(BaseModel):
    """
    Batch Image Filter Piece Output Model
    """

    image_base64_strings: List[Optional[str]] = Field(
        description="Base64 encoded strings of output images. Length always matches input_images.",
    )
    image_file_paths: List[Optional[str]] = Field(
        description="Paths to output image files. Length always matches input_images.",
    )
    input_count: int = Field(
        description="Number of input images provided.",
    )
    successful_count: int = Field(
        description="Number of successfully processed images.",
    )
    failed_count: int = Field(
        description="Number of failed images.",
    )
