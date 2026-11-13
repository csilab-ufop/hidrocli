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
Job orchestration: compose extract, transform and load for each job.
"""

import logging, time
logger = logging.getLogger(__name__)

from concurrent.futures import ThreadPoolExecutor, as_completed
from threading          import Thread, Lock
from queue              import Queue

from datetime    import datetime, timedelta
from dataclasses import dataclass

from typing import Optional, List

from hidrocli.database.client import *
from hidrocli.database.hidro  import *

from hidrocli.etl.extract    import request_job_data, request_token
from hidrocli.etl.transform  import convert_json_items, validate_series_items, validate_series_items_date
from hidrocli.etl.load       import db_writer
from hidrocli.etl.specs      import JobConfig, JobSpec, SPECS

MAX_WORKERS      = None
BATCH_SIZE       = None
SKIP_SERIES_JOBS = False
SKIP_FOR         = []
RUN_FOR          = []
STATIONS         = []
SAVE_JSON        = False
JSON_DIR         = "json"


@dataclass
class SerieStationData:
    """ Data class to receive Series Job data when starting a job."""

    station_code: int
    """ Station code which data will be requested."""

    start_date: DateTime
    """ Start date which data will be requested"""

    end_date: DateTime
    """ End date which data will be requested"""

    def __iter__(self):
        return iter((self.station_code, self.start_date, self.end_date))


@dataclass
class QueueData:
    """ Data class to hold expected interface data by writer thread."""

    spec:        JobSpec
    job:         HidroJob
    items:       dict
    worker_time: float
    stop_signal: bool

    def __iter__(self):
        return iter((
            self.spec,
            self.job,
            self.items,
            self.worker_time,
            self.stop_signal
        ))


_token_cache: Optional[Token] = None
"""Private Token global to control expiration time."""


def get_token() -> str:
    """Authenticate and return access token.

    :returns: Valid token for requesition
    """

    global _token_cache
    if _token_cache is None:
        _token_cache = get_token_model()

    if _token_cache is not None and datetime.now() < _token_cache.Expires:
        logger.verbose(f"Token is valid. ({_token_cache.Expires})")
        return _token_cache.Token

    logger.info("No valid token present, requesting.")
    credentials = get_credentials()
    token, expires = request_token(credentials.ID, credentials.Password)
    if _token_cache is None:
        _token_cache = Token()
    _token_cache.Token   = token
    _token_cache.Expires = expires

    if count_client(Token):
        update_token(_token_cache.RegistroID, token, expires)
    else:
        add_token(credentials.ID, token, expires)

    logger.info("Token acquired and cached.")
    return token


def check_base_job(job_config: JobConfig.Base) -> None:
    """Checks each HidroJob and request/update them.

    :param job: Current Job to check, insert and update.
    :returns: Nothing.
    """

    spec    = SPECS[job_config]
    filters = create_job_filters(job_config, None, last_check=False)
    if not count_job(job_config, filters):
        logger.info(f"Creating jobs for {job_config}.")
        jobs = []
        if job_config == JobConfig.Base.STATION:
            for state in get_states():
                jobs.append(spec.job_model(
                    HidroTable = job_config,
                    Status     = JobConfig.Status.PENDING.value,
                    UF         = state.Sigla
                ))
        else:
            jobs.append(spec.job_model(
                HidroTable = job_config,
                Status     = JobConfig.Status.PENDING.value
            ))
        insert_jobs(jobs)
        check_base_job(job_config)
    else:
        status  = [JobConfig.Status.FAILED.value, JobConfig.Status.PENDING.value]
        filters = create_job_filters(job_config, status, last_check=True)
        count   = count_job(job_config, filters)
        if count:
            logger.info(f"Initiating jobs for {job_config}")
            trigger_job(job_config, filters)
            check_base_job(job_config)
        else:
            logger.info(f"No pending jobs for {job_config}.")


def check_series_job(job_config: JobConfig) -> None:
    """Checks an JobConfig.
    Create jobs if there is no entries and start pending jobs requisition.
    """

    filters = create_job_filters(job_config, None, last_check=False)
    if not count_job(job_config, filters):
        logger.info(f"Creating jobs for {job_config}")
        period_data = get_period(job_config).all()
        create_series_jobs(period_data, job_config)
        check_series_job(job_config)
    else:
        update_series_job(job_config)
        status = [JobConfig.Status.FAILED.value, JobConfig.Status.PENDING.value]
        filters = create_job_filters(job_config, status, last_check=False,
                                     stations=STATIONS, max_retries=True)
        count = count_job(job_config, filters)
        if count:
            logger.info(f"Initiating {count} jobs for {job_config}")
            trigger_job(job_config, filters)
            check_series_job(job_config)
        else:
            logger.info(f"No pending jobs for {job_config}.")


def create_series_jobs(stations_data: List[SerieStationData], job_config: JobConfig) -> None:
    """ Creates Series Jobs for each SerieStationData received for a given JobConfig.
    Preprocess all years from "Start Date" to "End Date" that will become a job request.
    """
    start = time.time()
    jobs = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_period, *data, job_config)
                   for data in stations_data]
        for future in as_completed(futures):
            try:
                processed_jobs = future.result()
                jobs.extend(processed_jobs)
            except Exception as e:
                logger.error(f"Error processing period: {e}")
    insert_jobs(jobs)
    elapsed = time.time() - start
    logger.info(f"Created {len(jobs)} jobs for {job_config} in {elapsed:.2f} seconds")


def process_period(station_code, start_date, end_date, job_config):
    """ Creates Series Jobs for each SerieStationData received for a given JobConfig.
    Preprocess all years from "Start Date" to "End Date" that will become a job request.
    """

    jobs = []
    formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"]
    for fmt in formats:
        try:
            start_date = datetime.strptime(start_date, fmt)
            break
        except Exception as e:
            continue
    if end_date is None:
        end_date = datetime.today() - timedelta(days=1)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        for fmt in formats:
            try:
                end_date = datetime.strptime(end_date, fmt)
                break
            except Exception as e:
                continue

    if start_date > end_date:
        logger.verbose(f"Bigger start date {start_date} than end date {end_date} for station {station_code}")
        jobs.append(SeriesJobs(
            HidroTable    = job_config,
            StationID     = station_code,
            FromDate      = start_date,
            ToDate        = end_date,
            Status        = JobConfig.Status.CORRUPTED.value,
        ))
        return jobs
    total_years  = end_date.year - start_date.year
    current_year = start_date
    for count_year in range(1, total_years+1):
        next_year = current_year.replace(year=current_year.year+1)
        if next_year > end_date:
            next_year = end_date
        jobs.append(SeriesJobs(
            StationID  = station_code,
            FromDate   = current_year,
            ToDate     = next_year,
            Status     = JobConfig.Status.PENDING.value,
            HidroTable = job_config
        ))
        if next_year < end_date:
            current_year = next_year
        else:
            break
    return jobs


def update_series_job(job_config: JobConfig) -> None:
    station_ids = get_period(job_config, only_code=True, with_null_end_date=True).scalars().all()
    jobs = get_lesser_year(job_config, station_ids)
    yesterday = (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    for job in jobs:
        if job.ToDate < yesterday:
            logger.trace(f"Updating job id {job.ID} ToDate {job.ToDate} to {yesterday}")
            job.Status = JobConfig.Status.PENDING.value
            job.ToDate = yesterday
        else:
            logger.verbose(f"No updates for job id {job.ID}")
    update_jobs(jobs, job_config)


write_queue: Queue[QueueData] = Queue()
def trigger_job(job_config: JobConfig, filters) -> None:
    """ Triggers an Thread Worker for each pending or falied job entrie in DB for a given JobConfig."""

    writer = Thread(target=db_writer, args=(write_queue, BATCH_SIZE), daemon=True)
    writer.start()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(handle_job_request, job, job_config)
                   for job in get_jobs(job_config, filters)]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logger.error(f"[WORKER]: {e}")

    finish_queue = QueueData(
        spec        = SPECS[job_config],
        job         = None,
        items       = None,
        worker_time = 0,
        stop_signal = True
    )
    write_queue.put(finish_queue)
    writer.join()
    status_map = {1: "Pending", 2: "Failed", 5: "Completed"}
    counts = {status_map.get(s, f"Unknown({s})"): c for s, c in count_job_by_status(job_config)}
    logger.info(f"Pending: {counts.get('Pending', 0)}, Failed: {counts.get('Failed', 0)}, Completed: {counts.get('Completed', 0)}\n")


token_lock = Lock()
def handle_job_request(job: HidroJob, job_config: JobConfig) -> None:
    """ Request data of an HidroJob.
    Validate data on success return, and convert to ORM model before writing on Queue.
    """

    spec  = SPECS[job_config]
    start = time.time()
    with token_lock:
        token = get_token()
    success, items = request_job_data(job_config, token, job.to_params(),
                                      JSON_DIR if SAVE_JSON else None)

    if success:
        try:
            convert_json_items(spec, items)
            job.Status = JobConfig.Status.COMPLETED.value
            if spec.kind == "base":
                job.LastCheck = datetime.now()
            elif len(items) > 0:
                items = validate_series_items(job, spec, items)
                if len(items) > 0:
                    items = validate_series_items_date(job, spec, items)
        except Exception as e:
            logger.error(f"[WORKER JOB {job.ID}]: {e}, {items}, {type(items)}")
    else:
        job.Status = JobConfig.Status.FAILED.value
        if spec.kind == "series":
            job.Retries += 1
    elapsed = time.time() - start
    logger.verbose(f"[WORKER]: Job {job.ID} completed in {elapsed:.2f} seconds")
    queue_data = QueueData(
        spec        = spec,
        job         = job,
        items       = items,
        worker_time = elapsed,
        stop_signal = False
    )
    write_queue.put(queue_data)


def run():
    for job in JobConfig.Base:
        logger.info(f"====================================")
        check_base_job(job)
        logger.info(f"====================================\n")

    if SKIP_SERIES_JOBS:
        logger.info(f"Skiping series jobs.\n")
        return

    for job in JobConfig.Series:
        logger.info(f"====================================")
        if job in SKIP_FOR:
            logger.info(f"Skiping job for {job}.")
            logger.info(f"====================================\n")
            continue
        if len(RUN_FOR) > 0:
            if job not in RUN_FOR:
                logger.info(f"Skiping job for {job}.")
                logger.info(f"====================================\n")
                continue
        check_series_job(job)
        logger.info(f"====================================\n")
