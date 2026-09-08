import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from domino.schemas.deploy_mode import DeployModeType
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pieces.BatchHttpRequestPiece.models import InputModel
from pieces.BatchHttpRequestPiece.piece import BatchHttpRequestPiece


def test_rejects_invalid_max_concurrency():
    with pytest.raises(ValidationError):
        InputModel(max_concurrency=0)


def test_preserves_one_output_slot_per_request(tmp_path):
    piece = BatchHttpRequestPiece(DeployModeType.dry_run, "test_task", "test_dag")
    piece.results_path = str(tmp_path)

    response_ok = Mock()
    response_ok.content = b"image-a"
    response_ok.status_code = 200
    response_ok.raise_for_status.return_value = None

    response_error = Mock()
    response_error.status_code = 404
    response_error.raise_for_status.side_effect = Exception("not found")

    def fake_request(method, url, headers, json, timeout):
        if url.endswith("a.png"):
            return response_ok
        raise requests_error("not found")

    def requests_error(message):
        import requests

        return requests.RequestException(message)

    input_data = InputModel(
        requests=[
            {"url": "https://example.com/a.png"},
            {"url": "https://example.com/missing.png"},
        ],
        max_concurrency=8,
    )

    with patch("pieces.BatchHttpRequestPiece.piece.requests.request", side_effect=fake_request):
        output = piece.piece_function(input_data)

    assert output.requested_count == 2
    assert output.successful_count == 1
    assert output.failed_count == 1
    assert len(output.base64_bytes_data_list) == 2
    assert output.base64_bytes_data_list[0] is not None
    assert output.base64_bytes_data_list[1] is None
