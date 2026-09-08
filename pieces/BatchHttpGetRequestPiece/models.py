from typing import List, Optional

from pydantic import BaseModel, Field, conint


class RequestConfig(BaseModel):
    url: str = Field(
        description="URL to request.",
        json_schema_extra={"from_upstream": "never"},
    )
    bearer_token: Optional[str] = Field(
        default=None,
        description="Optional bearer token for this request.",
        json_schema_extra={"from_upstream": "never"},
    )


class InputModel(BaseModel):
    """
    Batch HTTP GET Request Piece Input Model
    """

    requests: List[RequestConfig] = Field(
        default=[],
        description="GET requests to execute.",
        json_schema_extra={"from_upstream": "never"},
    )
    timeout_seconds: int = Field(
        default=10,
        description="Request timeout in seconds.",
    )
    max_concurrency: conint(ge=1) = Field(
        default=8,
        description="Maximum number of concurrent requests.",
    )


class OutputModel(BaseModel):
    """
    Batch HTTP GET Request Piece Output Model
    """

    base64_bytes_data_list: List[Optional[str]] = Field(
        description="Base64 encoded response bodies. Length always matches the number of input requests.",
    )
    response_file_paths: List[Optional[str]] = Field(
        description="Paths to response body files. Length always matches the number of input requests.",
    )
    requested_count: int = Field(
        description="Number of requests provided.",
    )
    successful_count: int = Field(
        description="Number of successful requests.",
    )
    failed_count: int = Field(
        description="Number of failed requests.",
    )
