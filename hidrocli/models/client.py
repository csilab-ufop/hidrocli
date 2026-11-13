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
""" Provides models for Client Database. """

from sqlalchemy import (
    Column, Integer, String,
    DateTime, ForeignKey, BigInteger,
    SmallInteger
)
from sqlalchemy.orm import declarative_base
from datetime import datetime

ClientBase = declarative_base()

class Credentials(ClientBase):
    """ Client authentication credentials.

    Stores the ANA API username and password used to request access tokens.
    """

    __tablename__ = 'Credentials'

    RegistroID = Column(Integer, primary_key=True, autoincrement=True)
    """ int: unique record identifier. """

    ID         = Column(String, nullable=False)
    """ string: ANA API username or client identifier. """

    Password   = Column(String, nullable=False)
    """ string: ANA API password. """


class Token(ClientBase):
    """ Cached ANA API access token.

    A valid token is reused until ``Expires``; otherwise a new token is
    requested with the stored credentials.
    """

    __tablename__ = 'Token'

    RegistroID   = Column(Integer, primary_key=True, autoincrement=True)
    """ int: unique record identifier. """

    CredentialID = Column(Integer, ForeignKey('Credentials.ID'), nullable=False)
    """ int: foreign key to the credentials used to obtain the token. """

    Token        = Column(String)
    """ string: ANA API access token. """

    Expires      = Column(DateTime)
    """ datetime: token expiration time. """


class HidroJob(ClientBase):
    """ Shared fields for a persistent job-queue entry.

    Concrete job models add the fields needed to build their API request.
    """

    __abstract__ = True

    ID         = Column(Integer, primary_key=True, autoincrement=True)
    """ int: unique job identifier. """

    HidroTable = Column(String, nullable=False)
    """ string: target Hidro table and job name. """

    Status     = Column(SmallInteger, nullable=False)
    """
    int: job status.
    1 - Pending.
    2 - Failed.
    3 - Invalid.
    4 - Corrupted.
    5 - Completed.
    """

    def __iter__(self):
        """ Yield the job fields as key/value pairs. """
        yield from {
            "ID":         self.ID,
            "HidroTable": self.HidroTable,
            "Status":     self.Status
        }.items()

class BaseJobs(HidroJob):
    """ Jobs that refresh a reference (base) resource.

    Each row requests one Hidro table such as Bacia, Estado, or Estacao.
    """

    __tablename__ = 'BaseJobs'

    LastCheck  = Column(DateTime, default=datetime.now)
    """ datetime: last successful job check. """

    def __iter__(self):
        """ Yield the base-job fields as key/value pairs. """
        yield from super().__iter__()
        yield from { "LastCheck": self.LastCheck }.items()

    def to_params(self):
        """ Return the API query parameters for a base job (none). """
        return {}


class StationJobs(HidroJob):
    """ Jobs that refresh station inventory for one state. """

    __tablename__ = 'StationJobs'

    UF         = Column(String,   nullable=False)
    """ string: state abbreviation used in the API filter. """

    LastCheck  = Column(DateTime, default=datetime.now)
    """ datetime: last successful job check. """

    def __iter__(self):
        """ Yield the station-job fields as key/value pairs. """
        yield from super().__iter__()
        yield from {
            "UF":        self.UF,
            "LastCheck": self.LastCheck
        }.items()

    def to_params(self):
        """ Return the API query parameters for the station job. """
        return {"Unidade Federativa": f"{self.UF}"}


class SeriesJobs(HidroJob):
    """ Jobs that request a station time-series window.

    The API request uses the ``DATA_LEITURA`` date filter.
    """

    __tablename__ = 'SeriesJobs'

    StationID = Column(BigInteger, nullable=False)
    """ int: station code whose data will be requested. """

    FromDate  = Column(DateTime, nullable=False)
    """ datetime: start of the requested data window. """

    ToDate    = Column(DateTime, nullable=False)
    """ datetime: end of the requested data window. """

    Retries   = Column(Integer, default=0)
    """ int: number of failed attempts; job filters stop after 3. """

    def __iter__(self):
        """ Yield the series-job fields as key/value pairs. """
        yield from super().__iter__()
        yield from {
            "StationID": self.StationID,
            "FromDate":  self.FromDate,
            "ToDate":    self.ToDate,
            "Retries":   self.Retries
        }.items()

    def to_params(self):
        """ Return the API query parameters for the series job. """
        return {
            "Código da Estação":         self.StationID,
            "Tipo Filtro Data":          "DATA_LEITURA", # "DATA_ULTIMA_ATUALIZACAO"
            "Data Inicial (yyyy-MM-dd)": f"{self.FromDate.strftime('%Y-%m-%d')}",
            "Data Final (yyyy-MM-dd)":   f"{self.ToDate.strftime('%Y-%m-%d')}"
        }
