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

"""
Single source of truth for every Hidro job.

``JobSpec`` collapses the parallel ``job_name``-keyed maps (endpoint, model,
verify keys, period columns, dedupe/date/load strategy) that used to live
scattered across ``webservices.py``, ``database/*.py`` and ``jobs.py``.
"""

from dataclasses import dataclass
from enum import Enum, auto, StrEnum
from typing import Literal

from hidrocli.models.client import BaseJobs, StationJobs, SeriesJobs
from hidrocli.models.hidro import (
    Basin, CrossSection, DischargeMeasurement, Entity, FlowRate,
    Granulometry, Rain, RatingCurve, River, Sediments, Stage, State,
    Station, SubBasin, Township, WaterQuality,
)


class JobConfig:
    """ Hold basic config data for jobs. """

    class Base(StrEnum):
        """ Enum to hold basic resources data that does not require Threads. """

        BASIN     = "Bacia"
        SUB_BASIN = "SubBacia"
        ENTITY    = "Entidade"
        TOWNSHIP  = "Municipio"
        RIVER     = "Rio"
        STATE     = "Estado"
        STATION   = "Estacao"

    class Series(StrEnum):
        """ Enum to hold Hidro Jobs that will run with threads. """

        RAIN              = "Chuvas"
        DISCHARGE_SUMMARY = "ResumoDescarga"
        SEDIMENTS         = "Sedimentos"
        FLOW_RATE         = "Vazoes"
        GRANULOMETRY      = "Granulometria"
        DISCHARGE_FLOW    = "CurvaDescarga"
        WATER_QUALITY     = "QualAgua"
        CROSS_SECTION     = "PerfilTransversal"
        STAGE             = "Cotas"

    class Status(Enum):
        """ Enum to hold the result status of a job. """

        PENDING   = auto()
        FAILED    = auto()
        INVALID   = auto()
        CORRUPTED = auto()
        COMPLETED = auto()


@dataclass(frozen=True)
class JobSpec:
    """Declarative description of one Hidro job."""

    name: str                  # API key == table name == CLI choice
    kind: Literal["base", "series"]
    endpoint: str              # ANA WebService endpoint
    model: type                # Hidro ORM model written by this job
    job_model: type            # BaseJobs | StationJobs | SeriesJobs
    verify_keys: dict          # {model_attr: json_key} upsert identity
    dedupe_keys: tuple = ()    # json keys for dedupe; () == whole item
    date_key: str | None = None   # json key validated against the job window
    period_fields: tuple = ()  # Station (start, end) columns for job windows
    load: str = "upsert"       # "upsert" | "qa" | "cross_section"

    @property
    def required_keys(self) -> set:
        """JSON keys an item must carry to survive validation."""
        keys = set(self.verify_keys.values())
        if self.date_key:
            keys.add(self.date_key)
        return keys


# Period columns are Station table attributes, grouped by series family.
_PERIOD_CHUVA = (Station.PeriodoRegistradorChuvaInicio, Station.PeriodoRegistradorChuvaFim)
_PERIOD_DESC  = (Station.PeriodoDescLiquidaInicio, Station.PeriodoDescLiquidaFim)
_PERIOD_SED   = (Station.PeriodoSedimentosInicio, Station.PeriodoSedimentosFim)
_PERIOD_NIVEL = (Station.PeriodoRegistradorNivelInicio, Station.PeriodoRegistradorNivelFim)
_PERIOD_QA    = (Station.PeriodoQualAguaInicio, Station.PeriodoQualAguaFim)

_ESTACAO_DATA = {"EstacaoCodigo": "codigoestacao", "Data": "Data_Hora_Dado"}


def _specs() -> list[JobSpec]:
    base = lambda n, e, m, j, v: JobSpec(n, "base", e, m, j, v)
    series = lambda n, e, m, v, dedupe, date, period, load="upsert": JobSpec(
        n, "series", e, m, SeriesJobs, v, dedupe, date, period, load,
    )

    return [
        base("Bacia",     "/EstacoesTelemetricas/HidroBacia/v1",             Basin,    BaseJobs,    {"Codigo": "codigobacia"}),
        base("SubBacia",  "/EstacoesTelemetricas/HidroSubBacia/v1",          SubBasin, BaseJobs,    {"Codigo": "codigosubbacia"}),
        base("Entidade",  "/EstacoesTelemetricas/HidroEntidade/v1",          Entity,   BaseJobs,    {"Codigo": "codigoentidade"}),
        base("Municipio", "/EstacoesTelemetricas/HidroMunicipio/v1",         Township, BaseJobs,    {"Codigo": "codigomunicipio"}),
        base("Rio",       "/EstacoesTelemetricas/HidroRio/v1",               River,    BaseJobs,    {"Codigo": "codigorio"}),
        base("Estado",    "/EstacoesTelemetricas/HidroUF/v1",                State,    BaseJobs,    {"Codigo": "codigouf"}),
        base("Estacao",   "/EstacoesTelemetricas/HidroInventarioEstacoes/v1", Station,  StationJobs, {"Codigo": "codigoestacao"}),

        series("Chuvas",            "/EstacoesTelemetricas/HidroSerieChuva/v1",             Rain,                _ESTACAO_DATA, ("codigoestacao", "Data_Hora_Dado"), "Data_Hora_Dado",    _PERIOD_CHUVA),
        series("ResumoDescarga",    "/EstacoesTelemetricas/HidroSerieResumoDescarga/v1",    DischargeMeasurement, _ESTACAO_DATA, (), "Data_Hora_Dado", _PERIOD_DESC),
        series("CurvaDescarga",     "/EstacoesTelemetricas/HidroSerieCurvaDescarga/v1",     RatingCurve, {
            "EstacaoCodigo": "codigoestacao",
            "NumeroCurva": "Numero_Curva",
            "PeriodoValidadeInicio": "Periodo_Validade_Inicio",
            "PeriodoValidadeFim": "Periodo_Validade_Fim",
        }, ("codigoestacao", "Numero_Curva", "Periodo_Validade_Inicio", "Periodo_Validade_Fim"), None, _PERIOD_DESC),
        series("Sedimentos",        "/EstacoesTelemetricas/HidroSerieSedimentos/v1",        Sediments,            _ESTACAO_DATA, ("codigoestacao", "Data_Hora_Dado"), "Data_Hora_Dado",    _PERIOD_SED),
        series("QualAgua",          "/EstacoesTelemetricas/HidroSerieQA/v1",               WaterQuality,         _ESTACAO_DATA, ("codigoestacao", "Data_Hora_Dado"), "Data_Hora_Dado",    _PERIOD_QA, load="qa"),
        series("Cotas",             "/EstacoesTelemetricas/HidroSerieCotas/v1",             Stage,                _ESTACAO_DATA, ("codigoestacao", "Data_Hora_Dado"), "Data_Hora_Dado",    _PERIOD_NIVEL),
        series("Granulometria",     "/EstacoesTelemetricas/HidroSerieGranulometria/v1",     Granulometry, {
            "EstacaoCodigo": "codigoestacao",
            "Data": "Data_Dado",
            "HoraInicial": "Hora_Inicial",
            "HoraFinal": "Hora_Final",
        }, ("codigoestacao", "Data_Dado", "Hora_Inicial", "Hora_Final"), "Data_Dado",       _PERIOD_SED),
        series("PerfilTransversal", "/EstacoesTelemetricas/HidroSeriePerfilTransversal/v1", CrossSection,        {"RegistroID": "Registro_ID"}, ("Registro_ID",), "Data_Hora_Medicao", _PERIOD_DESC, load="cross_section"),
        series("Vazoes",            "/EstacoesTelemetricas/HidroSerieVazao/v1",             FlowRate,             _ESTACAO_DATA, ("codigoestacao", "Data_Hora_Dado"), "Data_Hora_Dado",    _PERIOD_DESC),
    ]


SPECS: dict[str, JobSpec] = {spec.name: spec for spec in _specs()}
