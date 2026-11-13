# BSD 2-Clause License

# Copyright (c) 2026, base

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:

# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import pytest
from unittest.mock import patch, Mock

import requests
import json

from hidrocli.etl.extract import *

@patch('hidrocli.etl.extract.requests.get')
def test_request_hidro_ws_success(mock_get):
    """Test successful request returns JSON."""

    mock_response                   = Mock()
    mock_response.ok                = True
    mock_response.json.return_value = {"data": "test"}
    mock_get.return_value           = mock_response

    result = request_hidro_ws("/endpoint", {"Authorization": "Bearer token"})

    assert result == {"data": "test"}
    mock_get.assert_called_once_with(
        "https://www.ana.gov.br/hidrowebservice/endpoint",
        headers={"Authorization": "Bearer token"},
        params={},
        timeout=300
    )


@patch('hidrocli.etl.extract.requests.get')
@patch('hidrocli.etl.extract.time.sleep')
def test_request_hidro_ws_error(mock_sleep, mock_get):
    """Test sleep on 503 code."""

    mock_response                   = Mock()
    mock_response.ok                = False
    mock_response.status_code       = 503
    mock_response.json.return_value = {"error": "Service Unavailable"}
    mock_get.return_value           = mock_response

    result = request_hidro_ws("/endpoint", {})

    assert result is None
    mock_sleep.assert_called_once_with(1)


@patch('hidrocli.etl.extract.requests.get')
def test_request_hidro_ws_json_exception(mock_get):
    """Test handling of JSON decode error on successful response."""

    mock_response                  = Mock()
    mock_response.ok               = True
    mock_response.json.side_effect = ValueError("Invalid JSON")
    mock_get.return_value          = mock_response

    result = request_hidro_ws("/endpoint", {})

    assert result is None


@patch('hidrocli.etl.extract.request_hidro_ws')
def test_request_token_success(mock_request):
    """Test successful token retrieval."""

    mock_request.return_value = {
        "items": {
            "tokenautenticacao": "abc123token",
            "validade": "Mon Jan 15 14:30:00 GMT-03:00 2024"
        }
    }

    result = request_token("client123", "pass456")

    assert result[0] == "abc123token"
    assert isinstance(result[1], datetime)
    assert result[1] == datetime(2024, 1, 15, 14, 30, 0)

    mock_request.assert_called_once_with(
        "/EstacoesTelemetricas/OAUth/v1",
        {
            "accept": "*/*",
            "Identificador": "client123",
            "Senha": "pass456"
        },
        {}
    )


@patch('hidrocli.etl.extract.request_hidro_ws')
@patch('hidrocli.etl.extract.time.sleep')
def test_request_token_retry_then_success(mock_sleep, mock_request):
    """Test retry logic when first attempt fails."""
    mock_request.side_effect = [
        Exception("Connection error"),
        {
            "items": {
                "tokenautenticacao": "token_after_retry",
                "validade": "Tue Feb 20 10:00:00 GMT-03:00 2024"
            }
        }
    ]

    result = request_token("client123", "pass456", max_retries=3, retry_delay=2)

    assert result[0]               == "token_after_retry"
    assert mock_request.call_count == 2
    mock_sleep.assert_called_once_with(2)


@patch('hidrocli.etl.extract.request_hidro_ws')
@patch('hidrocli.etl.extract.time.sleep')
def test_request_token_all_retries_fail(mock_sleep, mock_request):
    """Test that exception is raised after all retries fail."""

    with pytest.raises(Exception, match="Failed after"):
        request_token("client123", "pass456", max_retries=3, retry_delay=2)

    assert mock_request.call_count == 3
    assert mock_sleep.call_count   == 2


BASE_JOBS = ["Bacia", "SubBacia", "Entidade", "Municipio", "Rio", "Estado"]
SERIES_JOBS = ["Chuvas", "ResumoDescarga", "CurvaDescarga", "Sedimentos",
               "QualAgua", "Cotas", "Granulometria", "PerfilTransversal",
               "Vazoes"]
SERIES_PARAMS = {
    "Código da Estação":         "12345",
    "Tipo Filtro Data":          "DATA_LEITURA",
    "Data Inicial (yyyy-MM-dd)": "1927-05-01",
    "Data Final (yyyy-MM-dd)":   "1928-05-01",
}


def test_json_file_path_basic_jobs():
    """Base jobs are saved as <dir>/<Job>.json."""

    for job in BASE_JOBS:
        assert json_file_path(job, {}, "json") == os.path.join("json", f"{job}.json")


def test_json_file_path_estacao():
    """Station inventory is saved per state."""

    params = {"Unidade Federativa": "MG"}
    assert json_file_path("Estacao", params, "json") == os.path.join(
        "json", "Estacao", "Estacao_MG.json"
    )


def test_json_file_path_series():
    """Series jobs are saved per station and date window."""

    expected = os.path.join(
        "json", "{job}", "station_12345_1927-05-01_1928-05-01.json"
    )
    for job in SERIES_JOBS:
        assert json_file_path(job, SERIES_PARAMS, "json") == expected.format(job=job)


@patch('hidrocli.etl.extract.request_hidro_ws')
def test_request_job_data_saves_json(mock_request, tmp_path):
    """The fetched items are written with the cache formatting."""

    items = [{"codigobacia": "1", "Nome_Bacia": "RIO AMAZONAS"}]
    mock_request.return_value = {"items": items}

    success, result = request_job_data("Bacia", "token", {}, str(tmp_path))

    assert success is True
    assert result == items
    path = tmp_path / "Bacia.json"
    assert json.loads(path.read_text()) == items
    assert path.read_text().startswith("[\n  {")


@patch('hidrocli.etl.extract.request_hidro_ws')
def test_request_job_data_creates_series_directory(mock_request, tmp_path):
    """Saving a series payload creates its per-job directory."""

    mock_request.return_value = {"items": [{"codigoestacao": "12345"}]}

    request_job_data("Chuvas", "token", SERIES_PARAMS, str(tmp_path))

    path = tmp_path / "Chuvas" / "station_12345_1927-05-01_1928-05-01.json"
    assert path.is_file()
    assert json.loads(path.read_text()) == [{"codigoestacao": "12345"}]


@patch('hidrocli.etl.extract.request_hidro_ws')
def test_request_job_data_saves_empty_items(mock_request, tmp_path):
    """Empty responses are still recorded as an empty JSON array."""

    mock_request.return_value = {"items": []}

    success, items = request_job_data("Bacia", "token", {}, str(tmp_path))

    assert success is True
    assert items == []
    assert (tmp_path / "Bacia.json").read_text().strip() == "[]"


@patch('hidrocli.etl.extract.request_hidro_ws')
def test_request_job_data_does_not_save_without_dir(mock_request, tmp_path, monkeypatch):
    """Without --save-json nothing is written to disk."""

    monkeypatch.chdir(tmp_path)
    mock_request.return_value = {"items": [{"codigobacia": "1"}]}

    request_job_data("Bacia", "token", {})

    assert list(tmp_path.iterdir()) == []


@patch('hidrocli.etl.extract.save_json', side_effect=OSError("disk full"))
@patch('hidrocli.etl.extract.request_hidro_ws')
def test_request_job_data_save_failure_keeps_data(mock_request, mock_save):
    """A write failure must not turn a successful request into a failed job."""

    items = [{"codigobacia": "1"}]
    mock_request.return_value = {"items": items}

    success, result = request_job_data("Bacia", "token", {}, "json")

    assert success is True
    assert result == items
    mock_save.assert_called_once()
