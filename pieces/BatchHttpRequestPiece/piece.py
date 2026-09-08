import base64
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple

import requests
from domino.base_piece import BasePiece

from .models import InputModel, OutputModel, RequestConfig


class BatchHttpRequestPiece(BasePiece):

    def piece_function(self, input_data: InputModel):
        if not input_data.requests:
            raise ValueError("At least one request must be provided.")

        request_count = len(input_data.requests)
        request_key_to_indices = {}
        for index, request_config in enumerate(input_data.requests):
            request_key = self._request_key(request_config)
            request_key_to_indices.setdefault(request_key, []).append(index)
        unique_requests = [
            (indices[0], input_data.requests[indices[0]], indices)
            for indices in request_key_to_indices.values()
        ]
        max_workers = min(input_data.max_concurrency, len(unique_requests))
        self.logger.info(f"Requesting {request_count} URLs with up to {max_workers} concurrent workers.")
        self.logger.info(f"Deduped {request_count} requests down to {len(unique_requests)} unique requests.")

        base64_bytes_data_list = [None] * request_count
        response_file_paths = [None] * request_count

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(
                    self._fetch_request,
                    index,
                    request_config,
                    input_data.timeout_seconds,
                ): (index, indices)
                for index, request_config, indices in unique_requests
            }

            for future in as_completed(future_to_index):
                index, duplicate_indices = future_to_index[future]
                try:
                    result_index, encoded_body, response_file_path, status_code, error = future.result()
                except Exception as exc:
                    result_index = index
                    encoded_body = None
                    response_file_path = None
                    status_code = None
                    error = str(exc)

                for duplicate_index in duplicate_indices:
                    base64_bytes_data_list[duplicate_index] = encoded_body
                    response_file_paths[duplicate_index] = response_file_path
                if error:
                    self.logger.error(f"Request {result_index} failed: {error}")
                else:
                    self.logger.info(
                        f"Request {result_index} succeeded with status {status_code}; "
                        f"reused for {len(duplicate_indices)} output slots."
                    )

        if len(base64_bytes_data_list) != request_count:
            raise RuntimeError(
                f"Expected {request_count} outputs, got {len(base64_bytes_data_list)}."
            )
        if len(response_file_paths) != request_count:
            raise RuntimeError(
                f"Expected {request_count} response file paths, got {len(response_file_paths)}."
            )

        successful_count = sum(item is not None for item in base64_bytes_data_list)
        failed_count = request_count - successful_count
        self.logger.info(
            f"Completed {request_count} requests: {successful_count} succeeded, {failed_count} failed."
        )
        self._set_display_result(request_count, successful_count, failed_count)

        return OutputModel(
            base64_bytes_data_list=base64_bytes_data_list,
            response_file_paths=response_file_paths,
            requested_count=request_count,
            successful_count=successful_count,
            failed_count=failed_count,
        )

    def _fetch_request(
        self,
        index: int,
        request_config: RequestConfig,
        timeout_seconds: int,
    ) -> Tuple[int, Optional[str], Optional[str], Optional[int], Optional[str]]:
        headers = {}
        if request_config.bearer_token:
            headers["Authorization"] = f"Bearer {request_config.bearer_token}"

        json_body = None
        if request_config.body_json_data:
            try:
                json_body = json.loads(request_config.body_json_data)
            except json.JSONDecodeError as exc:
                return index, None, None, None, f"Invalid JSON body: {exc}"

        try:
            response = requests.request(
                method=request_config.method.value,
                url=request_config.url,
                headers=headers,
                json=json_body,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            return index, None, None, status_code, str(exc)

        encoded_body = base64.b64encode(response.content).decode("utf-8")
        response_file_path = str(Path(self.results_path) / f"response_{index}.bin")
        with open(response_file_path, "wb") as response_file:
            response_file.write(response.content)
        return index, encoded_body, response_file_path, response.status_code, None

    def _request_key(self, request_config: RequestConfig) -> Tuple[str, str, str, str]:
        return (
            request_config.url,
            request_config.method.value,
            request_config.bearer_token or "",
            request_config.body_json_data or "",
        )

    def _set_display_result(self, request_count: int, successful_count: int, failed_count: int):
        summary_path = str(Path(self.results_path) / "batch_http_request_summary.json")
        with open(summary_path, "w") as summary_file:
            json.dump(
                {
                    "requested_count": request_count,
                    "successful_count": successful_count,
                    "failed_count": failed_count,
                },
                summary_file,
                indent=2,
            )

        self.display_result = {
            "file_type": "json",
            "file_path": summary_path,
        }
