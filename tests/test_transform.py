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
from unittest.mock import MagicMock

from datetime import datetime

import hidrocli.etl.transform as transform
from hidrocli.etl.specs import JobConfig, SPECS


def _load_json_file(job_config):
    with open(f'./tests/json/{job_config}.json') as f:
        import json
        return json.load(f)


@pytest.mark.parametrize("job_config", [
    JobConfig.Base.BASIN,
    JobConfig.Series.RAIN,
])
def test_convert_json_items(job_config):
    items = transform.convert_json_items(SPECS[job_config], _load_json_file(job_config))
    match job_config:
        case JobConfig.Base.BASIN:
            for item in items:
                assert isinstance(item["Data_Ultima_Alteracao"], (datetime, type(None)))
                assert isinstance(item["Nome_Bacia"], str)
                assert isinstance(item["codigobacia"], int)
        case JobConfig.Series.RAIN:
            for item in items:
                for i in range(1, 32):
                    assert isinstance(item[f'Chuva_{i:02d}'], (float, type(None)))
                    assert isinstance(item[f'Chuva_{i:02d}_Status'], (int, type(None)))
                assert isinstance(item["Data_Ultima_Alteracao"], (datetime, type(None)))
                assert isinstance(item["Data_Hora_Dado"], (datetime, type(None)))
                assert isinstance(item["Maxima"], float)
                assert isinstance(item["Maxima_Status"], int)
                assert isinstance(item["Nivel_Consistencia"], int)
                assert isinstance(item["Numero_Dias_de_Chuva"], (int, type(None)))
                assert isinstance(item["Numero_Dias_de_Chuva_Status"], int)
                assert isinstance(item["Tipo_Medicao_Chuvas"], int)
                assert isinstance(item["Total"], float)
                assert isinstance(item["Total_Anual"], (float, type(None)))
                assert isinstance(item["Total_Anual_Status"], (int, type(None)))
                assert isinstance(item["Total_Status"], int)
                assert isinstance(item["codigoestacao"], int)


@pytest.mark.parametrize("job_config", [
    JobConfig.Series.RAIN,
])
def test_filter_repeated_series_items(job_config):
    items = transform.convert_json_items(SPECS[job_config], _load_json_file(job_config))
    filtered = transform.filter_repeated_series_items(SPECS[job_config], items)
    assert len(items) != len(filtered)


def test_validate_series_items_keeps_only_essential_keys():
    spec = SPECS["Chuvas"]
    job = MagicMock(ID=1)
    items = [
        {"codigoestacao": 1, "Data_Hora_Dado": datetime(2024, 6, 15)},
        {"codigoestacao": 2, "Data_Hora_Dado": datetime(2024, 6, 15), "Total": 5.0},
        {"codigoestacao": 3},   # missing Data_Hora_Dado
        {"foo": "bar"},         # missing both required keys
    ]
    result = transform.validate_series_items(job, spec, items)
    assert len(result) == 2


def test_validate_series_items_marks_failed_when_all_invalid():
    spec = SPECS["Chuvas"]
    job = MagicMock(ID=1)
    job.Status  = None
    job.Retries = 0
    result = transform.validate_series_items(job, spec, [{"x": 1}])
    assert result == []
    assert job.Status == JobConfig.Status.FAILED.value
    assert job.Retries == 1


def test_validate_series_items_date_filters_out_of_window():
    spec = SPECS["Chuvas"]
    job = MagicMock(ID=1)
    job.FromDate = datetime(2024, 1, 1)
    job.ToDate   = datetime(2024, 12, 31)
    items = [
        {"Data_Hora_Dado": datetime(2024, 6, 15, 10, 0, 0)},
        {"Data_Hora_Dado": datetime(2023, 6, 15, 10, 0, 0)},
    ]
    result = transform.validate_series_items_date(job, spec, items)
    assert len(result) == 1


def test_validate_series_items_date_skips_when_no_date_key():
    spec = SPECS["CurvaDescarga"]
    job = MagicMock(ID=1)
    items = [{"a": 1}, {"b": 2}]
    assert transform.validate_series_items_date(job, spec, items) is items
