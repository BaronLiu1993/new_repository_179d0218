import base64
from io import BytesIO

import pytest
from domino.schemas.deploy_mode import DeployModeType
from PIL import Image
from pydantic import ValidationError

from pieces.BatchImageFilterPiece.models import InputModel
from pieces.BatchImageFilterPiece.piece import BatchImageFilterPiece


def test_rejects_invalid_max_concurrency():
    with pytest.raises(ValidationError):
        InputModel(max_concurrency=0)


def test_preserves_one_output_slot_per_input(tmp_path):
    image = Image.new("RGB", (4, 4), color=(100, 150, 200))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded_image = base64.b64encode(buffer.getvalue()).decode("utf-8")

    piece = BatchImageFilterPiece(DeployModeType.dry_run, "test_task", "test_dag")
    piece.results_path = str(tmp_path)

    output = piece.piece_function(
        InputModel(
            input_images=[encoded_image, None],
            black_and_white=True,
            output_type="both",
            max_concurrency=8,
        )
    )

    assert output.input_count == 2
    assert output.successful_count == 1
    assert output.failed_count == 1
    assert len(output.image_base64_strings) == 2
    assert len(output.image_file_paths) == 2
    assert output.image_base64_strings[0] is not None
    assert output.image_file_paths[0] is not None
    assert output.image_base64_strings[1] is None
    assert output.image_file_paths[1] is None
