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

"""Round-trip tests: run the real E/T/L chain against committed real payloads.

Each job has a small representative payload under ``tests/json/`` (trimmed from
the live ANA download cache). These tests exist so that a wrong ``verify_keys``
json-key or a broken ``from_json`` mapping fails the suite without needing the
1.5M-file cache.
"""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from hidrocli.config import setup_logger
from hidrocli.database import DatabaseType, _setup_db
from hidrocli.database.hidro import count_hidro
from hidrocli.etl.load import write_data
from hidrocli.etl.specs import SPECS
from hidrocli.etl.transform import (
    convert_json_items,
    validate_series_items,
    validate_series_items_date,
)
from hidrocli.models.hidro import HidroBase

# Custom TRACE/VERBOSE levels only exist once setup_logger() has run; the
# E/T/L code calls logger.verbose/trace, so make this test order-independent.
setup_logger()

ALL_JOBS = list(SPECS)


@pytest.fixture
def db(tmp_path):
    connection = _setup_db(str(tmp_path / "hidro.db"), DatabaseType.HIDRO)
    with patch("hidrocli.database.hidro.HIDRO_DB", connection):
        yield connection
        HidroBase.metadata.drop_all(connection.engine)
        connection.close()


def load_fixture(name):
    with open(f"./tests/json/{name}.json") as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]


def fake_job(spec):
    job = SimpleNamespace(ID=0, Status=None, Retries=0)
    if spec.date_key:
        job.FromDate = datetime.min
        job.ToDate = datetime.max
    return job


def run_transform(spec, items):
    items = convert_json_items(spec, items)
    if spec.kind == "series":
        items = validate_series_items(fake_job(spec), spec, items)
        items = validate_series_items_date(fake_job(spec), spec, items)
    return items


def _normalize(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


@pytest.mark.parametrize("name", ALL_JOBS)
def test_roundtrip_loads_rows(name, db):
    """Each job's real payload survives convert -> validate -> load into a DB."""

    spec = SPECS[name]
    items = run_transform(spec, load_fixture(name))
    write_data(spec, [], items)
    assert count_hidro(spec.model) > 0


@pytest.mark.parametrize("name", ALL_JOBS)
def test_verify_keys_match_from_json(name):
    """The spec's verify_keys json-key agrees with the model's from_json."""

    spec = SPECS[name]
    item = convert_json_items(spec, load_fixture(name))[0]
    for model_attr, json_key in spec.verify_keys.items():
        assert json_key in item, f"{name}: {json_key!r} missing from payload"
        row = spec.model.from_json(item)
        assert _normalize(getattr(row, model_attr)) == _normalize(item[json_key]), (
            f"{name}: {model_attr} maps to {getattr(row, model_attr)!r} "
            f"but payload {json_key!r} is {item[json_key]!r}"
        )
