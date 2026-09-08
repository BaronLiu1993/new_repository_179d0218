import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

from domino.schemas.deploy_mode import DeployModeType
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pieces.BatchHttpRequestPiece.models import InputModel as HttpInputModel
from pieces.BatchHttpRequestPiece.piece import BatchHttpRequestPiece
from pieces.BatchImageFilterPiece.models import InputModel as ImageFilterInputModel
from pieces.BatchImageFilterPiece.piece import BatchImageFilterPiece


def _png_bytes(color):
    image = Image.new("RGB", (4, 4), color=color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_batch_http_file_outputs_feed_batch_image_filter(tmp_path):
    http_piece = BatchHttpRequestPiece(DeployModeType.dry_run, "http_task", "test_dag")
    http_piece.results_path = str(tmp_path / "http")
    Path(http_piece.results_path).mkdir()

    image_piece = BatchImageFilterPiece(DeployModeType.dry_run, "image_task", "test_dag")
    image_piece.results_path = str(tmp_path / "image")
    Path(image_piece.results_path).mkdir()

    image_bytes_by_url = {
        "https://example.com/0.png": _png_bytes((100, 150, 200)),
        "https://example.com/1.png": _png_bytes((200, 150, 100)),
        "https://example.com/2.png": _png_bytes((50, 75, 125)),
    }

    def fake_request(method, url, headers, json, timeout):
        response = Mock()
        response.content = image_bytes_by_url[url]
        response.status_code = 200
        response.raise_for_status.return_value = None
        return response

    with patch("pieces.BatchHttpRequestPiece.piece.requests.request", side_effect=fake_request):
        http_output = http_piece.piece_function(
            HttpInputModel(
                requests=[
                    {"url": "https://example.com/0.png"},
                    {"url": "https://example.com/1.png"},
                    {"url": "https://example.com/2.png"},
                ],
                max_concurrency=8,
            )
        )

    image_output = image_piece.piece_function(
        ImageFilterInputModel(
            input_images=http_output.response_file_paths,
            sepia=True,
            output_type="both",
            max_concurrency=8,
        )
    )

    assert http_output.requested_count == 3
    assert http_output.successful_count == 3
    assert len(http_output.response_file_paths) == 3
    assert image_output.input_count == 3
    assert image_output.successful_count == 3
    assert image_output.failed_count == 0
    assert all(image_output.image_base64_strings)
    assert all(Path(path).exists() for path in image_output.image_file_paths)
