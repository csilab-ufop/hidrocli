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

from hidrocli.models.client import BaseJobs, StationJobs, SeriesJobs
from hidrocli.etl.specs import SPECS, JobConfig


@pytest.mark.parametrize("name", list(JobConfig.Base) + list(JobConfig.Series))
def test_spec_exists_for_every_job(name):
    """Every Base/Series job value is registered in SPECS."""

    assert str(name) in SPECS


def test_specs_are_complete_and_consistent():
    """Every spec carries the fields the E/T/L layers need, consistently."""

    job_models = (BaseJobs, StationJobs, SeriesJobs)
    for name, spec in SPECS.items():
        assert spec.name == name
        assert spec.endpoint.startswith("/")
        assert spec.job_model in job_models
        assert spec.verify_keys, f"{name} has no verify_keys"
        for model_attr in spec.verify_keys:
            assert hasattr(spec.model, model_attr), \
                f"{name}.model has no column {model_attr}"
        if spec.kind == "series":
            assert spec.required_keys, f"{name} has no required keys"
            if spec.date_key is None:
                assert spec.name == "CurvaDescarga"


def test_specs_count():
    """There are 7 base jobs and 9 series jobs."""

    base   = [s for s in SPECS.values() if s.kind == "base"]
    series = [s for s in SPECS.values() if s.kind == "series"]
    assert len(base) == 7
    assert len(series) == 9
