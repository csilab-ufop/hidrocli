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
Load layer: upsert ORM rows and update job status.
"""

import logging, time
logger = logging.getLogger(__name__)

from hidrocli.database.client import update_jobs
from hidrocli.database import hidro as hidro_db
from hidrocli.models.hidro import VerticalCrossSection, WaterQualityStatus
from hidrocli.etl.specs import JobSpec
from hidrocli.etl.transform import filter_repeated_series_items


def handle_batch_update(model, verify_keys: dict, items):
    """Upsert ``items`` into ``model`` keyed by ``verify_keys``.

    Returns the list of newly created rows (not yet inserted).
    """

    hidro_session = hidro_db.HIDRO_DB.get_session()
    check_keys = verify_keys

    filter_values = {}
    for model_key, json_key in check_keys.items():
        filter_values[model_key] = [item.get(json_key) for item in items]

    query = hidro_session.query(model)
    for model_key, values in filter_values.items():
        attr = getattr(model, model_key)
        query = query.filter(attr.in_(values))

    existing = query.all()

    existing_map = {}
    for e in existing:
        key = tuple(getattr(e, k) for k in check_keys.keys())
        existing_map[key] = e

    new_entries = []
    for item in items:
        key = tuple(item.get(check_keys[k]) for k in check_keys.keys())
        entry = existing_map.get(key)
        if entry:
            entry.from_json(item)
            from sqlalchemy import inspect
            if inspect(entry).modified:
                logger.info(f"Updated {model.__tablename__} entry code {key}.")
                hidro_session.merge(entry)
                hidro_session.commit()
            else:
                logger.verbose(f"No Updates for {model.__tablename__} entry code {key}.")
        else:
            new_entries.append(model.from_json(item))
            logger.verbose(f"New {model.__tablename__} entry code {key}.")
    hidro_session.close()
    return new_entries


def write_data(spec: JobSpec, jobs, items) -> float:
    """Insert data into DB and update the jobs as well."""

    start_time = time.perf_counter()
    entries = []
    if len(items) > 0:
        filtered_items = items
        if spec.kind == "series":
            filtered_items = filter_repeated_series_items(spec, items)

        if spec.load == "upsert":
            entries = handle_batch_update(spec.model, spec.verify_keys, filtered_items)
            if entries:
                hidro_db.insert_hidro(entries)

        elif spec.load == "qa":
            entries = handle_batch_update(spec.model, spec.verify_keys, filtered_items)
            if entries:
                entries = hidro_db.insert_hidro(entries, False)
                entry_lookup = {(e.EstacaoCodigo, e.Data): e for e in entries}
                for item in filtered_items:
                    key = (item['codigoestacao'], item['Data_Hora_Dado'])
                    if key in entry_lookup:
                        item['Registro_ID'] = entry_lookup[key].RegistroID
                water_status_entries = handle_batch_update(
                    WaterQualityStatus, {"QualAguaID": "Registro_ID"}, filtered_items)
                if water_status_entries:
                    hidro_db.insert_hidro(water_status_entries)

        elif spec.load == "cross_section":
            entries = handle_batch_update(spec.model, spec.verify_keys, filtered_items)
            if entries:
                hidro_db.insert_hidro(entries, False)
            vertical_entries = [VerticalCrossSection.from_json(item) for item in items]
            hidro_db.insert_hidro(vertical_entries)

    if len(jobs) > 0:
        update_jobs(jobs, spec.name)
        logger.trace(f"[WRITER {spec.name}]: Updated {len(jobs)} jobs")
    elapsed_time = time.perf_counter() - start_time
    if entries:
        logger.trace(f"[WRITER {spec.name}]: Inserted {len(entries)} entries in {elapsed_time} seconds")
    return elapsed_time


def db_writer(write_queue, batch_size) -> None:
    """Single Writer Thread running during a job.

    Consumes a queue written by each worker and writes data in batches.
    """

    batch_buffer = {"jobs": [], "data": []}
    total_data     = 0
    total_jobs     = 0

    worker_elapsed = 0
    total_elapsed  = 0
    insert_elapsed = 0
    batch_elapsed  = 0
    batch_start_time = None
    while True:
        try:
            spec, job, data, worker_time, stop_signal = write_queue.get()
            worker_elapsed += worker_time
            if job:
                batch_buffer["jobs"].append(job)
            if data:
                batch_buffer["data"].extend(data)
                if batch_start_time is None:
                    batch_start_time = time.time()

            if (len(batch_buffer["data"]) >= batch_size or
                len(batch_buffer["jobs"]) >= batch_size or stop_signal):
                if batch_start_time is not None:
                    batch_elapsed = time.time() - batch_start_time
                total_data     += len(batch_buffer["data"])
                total_jobs     += len(batch_buffer["jobs"])
                insert_elapsed  = write_data(spec,
                                             batch_buffer["jobs"],
                                             batch_buffer["data"])
                total_elapsed += batch_elapsed + insert_elapsed

                logger.verbose(f"""[TIMER {spec.name}]: """
                               f"""Time to reach batch: {batch_elapsed}, """
                               f"""Time to insert batch: {insert_elapsed}. """)

                logger.info(f"""[WRITER {spec.name}]: """
                            f"""Total processed Data: {total_data}, """
                            f"""Total finished Jobs: {total_jobs}. """)
                logger.trace(f"""[TIMER {spec.name}]: """
                            f"""Total worker elapsed: {worker_elapsed}, """
                            f"""Total writer elapsed: {total_elapsed}.""")

                batch_buffer["jobs"].clear()
                batch_buffer["data"].clear()
                batch_start_time = None

            if stop_signal:
                logger.info(f"""[WRITER]: Finished jobs for {spec.name} """
                            f"""Total processed Data: {total_data}, """
                            f"""Total finished Jobs: {total_jobs}.""")
                logger.info(f"""[WRITER]: Total worker elapsed: {worker_elapsed}, """
                            f"""Total writer elapsed: {total_elapsed}.""")
                break;

        except Exception as e:
            logger.error(f"[WRITER]: db_writer exception: {e}")
            raise

        finally:
            write_queue.task_done()
