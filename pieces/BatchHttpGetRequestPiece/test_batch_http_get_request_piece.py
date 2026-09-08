import base64
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from domino.schemas.deploy_mode import DeployModeType
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pieces.BatchHttpGetRequestPiece.models import InputModel
from pieces.BatchHttpGetRequestPiece.piece import BatchHttpGetRequestPiece


def test_rejects_invalid_max_concurrency():
    with pytest.raises(ValidationError):
        InputModel(max_concurrency=0)


def test_processes_one_valid_request(tmp_path):
    piece = BatchHttpGetRequestPiece(DeployModeType.dry_run, "test_task", "test_dag")
    piece.results_path = str(tmp_path)

    response = Mock()
    response.content = b"image-a"
    response.status_code = 200
    response.raise_for_status.return_value = None

    input_data = InputModel(
        requests=[
            {
                "url": "https://example.com/a.png",
                "bearer_token": "token-a",
            },
        ],
        timeout_seconds=10,
        max_concurrency=8,
    )

    with patch("pieces.BatchHttpGetRequestPiece.piece.requests.request", return_value=response) as request_mock:
        output = piece.piece_function(input_data)

    assert output.requested_count == 1
    assert output.successful_count == 1
    assert output.failed_count == 0
    assert output.base64_bytes_data_list == [base64.b64encode(b"image-a").decode("utf-8")]
    assert len(output.response_file_paths) == 1
    assert Path(output.response_file_paths[0]).read_bytes() == b"image-a"
    request_mock.assert_called_once_with(
        method="GET",
        url="https://example.com/a.png",
        headers={"Authorization": "Bearer token-a"},
        json=None,
        timeout=10,
    )
    assert piece.display_result["file_type"] == "json"
    assert Path(piece.display_result["file_path"]).exists()


def test_processes_multiple_valid_requests(tmp_path):
    piece = BatchHttpGetRequestPiece(DeployModeType.dry_run, "test_task", "test_dag")
    piece.results_path = str(tmp_path)

    responses_by_url = {}
    for index, image_bytes in enumerate([b"image-a", b"image-b", b"image-c"]):
        response = Mock()
        response.content = image_bytes
        response.status_code = 200 + index
        response.raise_for_status.return_value = None
        responses_by_url[f"https://example.com/{index}.png"] = response

    def fake_request(method, url, headers, json, timeout):
        return responses_by_url[url]

    input_data = InputModel(
        requests=[
            {
                "url": "https://example.com/0.png",
            },
            {
                "url": "https://example.com/1.png",
                "bearer_token": "token-b",
            },
            {"url": "https://example.com/2.png"},
        ],
        timeout_seconds=10,
        max_concurrency=8,
    )

    with patch("pieces.BatchHttpGetRequestPiece.piece.requests.request", side_effect=fake_request) as request_mock:
        output = piece.piece_function(input_data)

    assert output.requested_count == 3
    assert output.successful_count == 3
    assert output.failed_count == 0
    assert output.base64_bytes_data_list == [
        base64.b64encode(b"image-a").decode("utf-8"),
        base64.b64encode(b"image-b").decode("utf-8"),
        base64.b64encode(b"image-c").decode("utf-8"),
    ]
    assert len(output.response_file_paths) == 3
    assert [Path(path).read_bytes() for path in output.response_file_paths] == [
        b"image-a",
        b"image-b",
        b"image-c",
    ]
    assert request_mock.call_count == 3
    assert all(call.kwargs["method"] == "GET" for call in request_mock.call_args_list)
    token_call = next(call for call in request_mock.call_args_list if call.kwargs["url"] == "https://example.com/1.png")
    assert token_call.kwargs["headers"] == {"Authorization": "Bearer token-b"}
    assert token_call.kwargs["json"] is None
    assert token_call.kwargs["timeout"] == 10

    summary = json.loads(Path(piece.display_result["file_path"]).read_text())
    assert summary == {
        "requested_count": 3,
        "successful_count": 3,
        "failed_count": 0,
    }


def test_dedupes_duplicate_requests(tmp_path):
    piece = BatchHttpGetRequestPiece(DeployModeType.dry_run, "test_task", "test_dag")
    piece.results_path = str(tmp_path)

    responses_by_url = {}
    for url, image_bytes in {
        "https://example.com/a.png": b"image-a",
        "https://example.com/b.png": b"image-b",
    }.items():
        response = Mock()
        response.content = image_bytes
        response.status_code = 200
        response.raise_for_status.return_value = None
        responses_by_url[url] = response

    def fake_request(method, url, headers, json, timeout):
        return responses_by_url[url]

    input_data = InputModel(
        requests=[
            {"url": "https://example.com/a.png"},
            {"url": "https://example.com/b.png"},
            {"url": "https://example.com/a.png"},
        ],
        max_concurrency=8,
    )

    with patch("pieces.BatchHttpGetRequestPiece.piece.requests.request", side_effect=fake_request) as request_mock:
        output = piece.piece_function(input_data)

    assert request_mock.call_count == 2
    assert output.requested_count == 3
    assert output.successful_count == 3
    assert output.failed_count == 0
    assert output.base64_bytes_data_list[0] == output.base64_bytes_data_list[2]
    assert output.response_file_paths[0] == output.response_file_paths[2]
    assert Path(output.response_file_paths[0]).read_bytes() == b"image-a"


def test_preserves_one_output_slot_per_request(tmp_path):
    piece = BatchHttpGetRequestPiece(DeployModeType.dry_run, "test_task", "test_dag")
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

    with patch("pieces.BatchHttpGetRequestPiece.piece.requests.request", side_effect=fake_request):
        output = piece.piece_function(input_data)

    assert output.requested_count == 2
    assert output.successful_count == 1
    assert output.failed_count == 1
    assert len(output.base64_bytes_data_list) == 2
    assert len(output.response_file_paths) == 2
    assert output.base64_bytes_data_list[0] is not None
    assert output.base64_bytes_data_list[1] is None
    assert Path(output.response_file_paths[0]).read_bytes() == b"image-a"
    assert output.response_file_paths[1] is None
    assert piece.display_result["file_type"] == "json"
    assert Path(piece.display_result["file_path"]).exists()
