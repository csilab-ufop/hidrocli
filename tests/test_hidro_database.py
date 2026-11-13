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
from unittest.mock import patch

from datetime import datetime

from hidrocli.database import *
from hidrocli.database import _setup_db
from hidrocli.database.hidro import *

@pytest.fixture
def hidro_db(tmp_path):

    db_path = str(tmp_path / "hidro.db")
    db_type = DatabaseType.HIDRO
    connection = _setup_db(db_path, db_type)
    with patch('hidrocli.database.hidro.HIDRO_DB', connection):
        yield connection
        HidroBase.metadata.drop_all(connection.engine)
        connection.close()


def test_create_period_statement_uses_spec_period_fields():
    chuvas = str(create_period_statement("Chuvas", only_code=False, with_null_end_date=False))
    assert "PeriodoRegistradorChuvaInicio" in chuvas
    assert "PeriodoRegistradorChuvaFim" in chuvas

    cotas = str(create_period_statement("Cotas", only_code=False, with_null_end_date=False))
    assert "PeriodoRegistradorNivelInicio" in cotas

    vazoes = str(create_period_statement("Vazoes", only_code=False, with_null_end_date=False))
    assert "PeriodoDescLiquidaInicio" in vazoes


def test_create_period_statement_only_code_skips_end_column():
    stmt = create_period_statement("Chuvas", only_code=True, with_null_end_date=True)
    text = str(stmt)
    assert "Codigo" in text
    assert "IS NULL" in text.upper()


def test_get_period_returns_stations_with_period(hidro_db):
    session = hidro_db.get_session()
    session.add(Station(
        Codigo=12345,
        PeriodoRegistradorChuvaInicio=datetime(2020, 1, 1),
        PeriodoRegistradorChuvaFim=datetime(2021, 1, 1),
    ))
    session.commit()
    session.close()

    rows = get_period("Chuvas").all()
    assert len(rows) == 1
    assert rows[0][0] == 12345
