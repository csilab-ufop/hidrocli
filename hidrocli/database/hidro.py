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

import logging
logger = logging.getLogger(__name__)

from typing import List

from sqlalchemy import select

from hidrocli.models.hidro  import *
from hidrocli.etl.specs     import SPECS

HIDRO_DB = None


def insert_hidro(collection: List[HidroBase], expire = True) -> List[HidroBase]:
    """ Insert a list of Hidro ORM Model into Hidro Database"""

    hidro_session = HIDRO_DB.get_session()
    hidro_session.expire_on_commit = expire
    hidro_session.add_all(collection)
    hidro_session.flush()
    hidro_session.commit()
    hidro_session.close()
    return collection


def count_hidro(model: HidroBase):
    """ Counts a given Model in Hidro Database. """

    hidro_session = HIDRO_DB.get_session()
    count_model   = hidro_session.query(model).count()
    hidro_session.close()
    return count_model


def get_states() -> State:
    """ Returns registered States in Hidro Database. """

    hidro_session = HIDRO_DB.get_session()
    states = hidro_session.query(State).filter(State.CodigoIBGE.isnot(None)).all()
    hidro_session.close()
    return states


def get_period(model_name: str, only_code=False, with_null_end_date=False):
    """ Returns stations with initial and final periods for an given table in Hidro Database. """

    statement = create_period_statement(model_name, only_code, with_null_end_date)
    hidro_session = HIDRO_DB.get_session()
    period_data = hidro_session.execute(statement)
    hidro_session.close()
    return period_data


def create_period_statement(model_name, only_code: bool, with_null_end_date: bool):
    """ Build the station-period SELECT for a series job from its ``JobSpec``. """

    start_col, end_col = SPECS[model_name].period_fields
    columns = [Station.Codigo]
    if not only_code:
        columns.extend([start_col, end_col])
    statement = select(*columns).where(start_col.isnot(None))
    if with_null_end_date:
        statement = statement.where(end_col.is_(None))
    return statement
