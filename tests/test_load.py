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

from unittest.mock import patch, MagicMock
from datetime import datetime

from hidrocli.models.hidro import VerticalCrossSection, WaterQualityStatus
from hidrocli.etl.load import write_data
from hidrocli.etl.specs import SPECS


@patch('hidrocli.etl.load.update_jobs')
@patch('hidrocli.etl.load.handle_batch_update')
@patch('hidrocli.database.hidro.insert_hidro')
def test_write_data_upsert(mock_insert, mock_handle, mock_update):
    spec = SPECS["Chuvas"]
    items = [{"codigoestacao": 1, "Data_Hora_Dado": datetime(2024, 1, 1)}]
    jobs = [MagicMock()]
    new_entries = [MagicMock()]
    mock_handle.return_value = new_entries

    write_data(spec, jobs, items)

    mock_handle.assert_called_once()
    assert mock_handle.call_args[0][0] is spec.model
    assert mock_handle.call_args[0][1] == spec.verify_keys
    mock_insert.assert_called_once_with(new_entries)
    mock_update.assert_called_once_with(jobs, spec.name)


@patch('hidrocli.etl.load.update_jobs')
@patch('hidrocli.etl.load.handle_batch_update')
@patch('hidrocli.database.hidro.insert_hidro')
def test_write_data_water_quality(mock_insert, mock_handle, mock_update):
    spec = SPECS["QualAgua"]
    item = {"codigoestacao": 1, "Data_Hora_Dado": datetime(2024, 1, 1)}
    items = [item]
    new_entries = [MagicMock(EstacaoCodigo=1, Data=datetime(2024, 1, 1), RegistroID=42)]
    mock_insert.return_value = new_entries
    mock_handle.side_effect = [new_entries, [MagicMock()]]

    write_data(spec, [], items)

    assert mock_handle.call_count == 2
    assert mock_handle.call_args_list[0][0][0] is spec.model
    assert mock_handle.call_args_list[0][0][1] == spec.verify_keys
    assert mock_handle.call_args_list[1][0][0] is WaterQualityStatus
    assert mock_handle.call_args_list[1][0][1] == {"QualAguaID": "Registro_ID"}
    assert mock_insert.call_count == 2
    assert item["Registro_ID"] == 42


@patch('hidrocli.etl.load.update_jobs')
@patch('hidrocli.etl.load.handle_batch_update')
@patch('hidrocli.database.hidro.insert_hidro')
def test_write_data_cross_section(mock_insert, mock_handle, mock_update):
    spec = SPECS["PerfilTransversal"]
    item = {"Registro_ID": 100, "Data_Hora_Medicao": datetime(2024, 1, 1)}
    mock_handle.return_value = [MagicMock()]

    write_data(spec, [], [item])

    assert mock_handle.call_count == 1
    assert mock_insert.call_count == 2
    assert mock_insert.call_args_list[0][0][1] is False
    vertical = mock_insert.call_args_list[1][0][0]
    assert len(vertical) == 1
    assert isinstance(vertical[0], VerticalCrossSection)
