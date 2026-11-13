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
Pure transform functions: convert API payloads, validate, and filter them.
"""

import json, logging
logger = logging.getLogger(__name__)

from datetime import datetime

from hidrocli.etl.specs import JobConfig, JobSpec


def convert_json_items(spec: JobSpec, items):
    """Convert returned data by API to python types."""

    if isinstance(items, dict):
        items = [items]

    for item in items:
        for key, value in item.items():
            if isinstance(value, str):
                try:
                    item[key] = json.loads(value)
                except (json.JSONDecodeError, ValueError):
                    if spec.name == "Granulometria":
                        formats = ["%Y-%m-%d %H:%M:%S.%f",
                                   "%Y-%m-%d %H:%M:%S",
                                   "%Y-%m-%d", "%H:%M:%S"]
                        for fmt in formats:
                            try:
                                item[key] = datetime.strptime(value, fmt)
                                break
                            except Exception as e:
                                continue
                    else:
                        try:
                            item[key] = datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")
                        except ValueError:
                            pass
    return items


def validate_series_items(job, spec: JobSpec, items):
    """Validate that returned data carries the keys needed for upsert."""

    required = spec.required_keys
    valid = []
    for index, item in enumerate(items):
        missing = required - item.keys()
        if missing:
            logger.verbose(f"[VALIDATE LEN Job {job.ID}] Item index {index} has missing key(s) {', '.join(sorted(missing))}")
            continue
        logger.verbose(f"[VALIDATE LEN Job {job.ID}] Appending item index {index}.")
        valid.append(item)

    if len(valid) == 0:
        job.Status   = JobConfig.Status.FAILED.value
        job.Retries += 1
    return valid


def validate_series_items_date(job, spec: JobSpec, items):
    """Validate if returned data by the API has the expected date interval."""

    if spec.date_key is None:
        return items

    valid = []
    for index, item in enumerate(items):
        try:
            date = item.get(spec.date_key)
            if date is None:
                logger.verbose(f"Item index {index} has missing key {spec.date_key}.")
                continue
            date = date.replace(hour=0, minute=0, second=0)
            if date < job.FromDate:
                logger.verbose(f"Item index {index} has invalid date {date}, lesser than job FromDate {job.FromDate}")
                continue
            if date > job.ToDate:
                logger.verbose(f"Item index {index} has invalid date {date}, bigger than job FromDate {job.ToDate}")
                continue

            valid.append(item)

        except Exception as e:
            logger.error(f"[VALIDATE DATE JOB {job.ID}] Error at index {index}: {e}, item type: {type(item)}")
            pass

    return valid


def filter_repeated_series_items(spec: JobSpec, items):
    """Filter repeated items before writing on database."""

    seen = set()
    filtered = []
    for index, item in enumerate(items):
        try:
            if not spec.dedupe_keys:
                key = tuple(sorted((k, str(v)) for k, v in item.items()))
            else:
                if spec.name == "CurvaDescarga":
                    item['Numero_Curva'] = str(item['Numero_Curva'])
                key = tuple(item[k] for k in spec.dedupe_keys)
            if key not in seen:
                seen.add(key)
                filtered.append(item)
            else:
                logger.verbose(f"[VALIDATE JOB]: Duplicated item: {key}")

        except Exception as e:
            logger.error(f"[FILTER] Error at index {index}: {e}")
            pass

    if filtered:
        items = filtered

    return items
