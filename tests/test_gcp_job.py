import json
from datetime import UTC, datetime

import pytest

from pharma_data_product.gcp_job import GcpLandingJob
from tests.test_models import valid_event


class FakeBlob:
    def __init__(self, content=""):
        self.content = content
        self.uploads = []

    def download_as_text(self, *, encoding="utf-8"):
        assert encoding == "utf-8"
        return self.content

    def upload_from_string(self, data, *, content_type):
        self.uploads.append((data, content_type))


class FakeBucket:
    def __init__(self, source_name, content):
        self.blobs = {source_name: FakeBlob(content)}

    def blob(self, name):
        return self.blobs.setdefault(name, FakeBlob())


class FakeStorage:
    def __init__(self, bucket):
        self.value = bucket

    def bucket(self, name):
        assert name == "raw-bucket"
        return self.value


class FakeBigQuery:
    def __init__(self, errors=None):
        self.calls = []
        self.errors = errors or {}

    def insert_rows_json(self, table, rows, *, row_ids):
        self.calls.append((table, rows, row_ids))
        return self.errors.get(table, [])


def fixed_now():
    return datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def make_job(content, bigquery=None):
    bucket = FakeBucket("incoming/events.ndjson", content)
    query = bigquery or FakeBigQuery()
    job = GcpLandingJob(
        storage=FakeStorage(bucket),
        bigquery=query,
        bucket="raw-bucket",
        object_name="incoming/events.ndjson",
        raw_table="project.raw.batch_event",
        quality_table="project.ops.data_quality_issue",
        now=fixed_now,
    )
    return job, bucket, query


def test_lands_valid_rows_with_event_ids():
    content = "\n".join(json.dumps(valid_event(event_id=value)) for value in ("evt-a", "evt-b"))
    job, _, query = make_job(content)

    result = job.run()

    assert (result.input_count, result.accepted_count, result.quarantined_count) == (2, 2, 0)
    table, rows, row_ids = query.calls[0]
    assert table == "project.raw.batch_event"
    assert row_ids == ["evt-a", "evt-b"]
    assert rows[0]["source_object"] == "gs://raw-bucket/incoming/events.ndjson"
    assert rows[0]["ingested_at"] == "2026-11-16T12:00:00+00:00"


def test_quarantines_invalid_lines_to_bigquery_and_storage():
    content = json.dumps(valid_event(event_id="accepted")) + "\n{not-json\n[]\n"
    job, bucket, query = make_job(content)

    result = job.run()

    assert (result.input_count, result.accepted_count, result.quarantined_count) == (3, 1, 2)
    assert result.quarantine_object.startswith("quarantine/20261116T120000Z-")
    assert [call[0] for call in query.calls] == [
        "project.raw.batch_event",
        "project.ops.data_quality_issue",
    ]
    uploaded = bucket.blob(result.quarantine_object).uploads
    assert len(uploaded) == 1
    assert uploaded[0][1] == "application/x-ndjson"
    issues = [json.loads(line) for line in uploaded[0][0].splitlines()]
    assert len(issues) == 2
    assert all(issue["raw_digest"] for issue in issues)


def test_fails_when_bigquery_reports_insert_errors():
    query = FakeBigQuery(errors={"project.raw.batch_event": [{"index": 0}]})
    job, _, _ = make_job(json.dumps(valid_event()), query)

    with pytest.raises(RuntimeError, match="raw insert returned 1"):
        job.run()


def test_rejects_empty_configuration():
    bucket = FakeBucket("incoming/events.ndjson", "")
    with pytest.raises(ValueError, match="raw_table"):
        GcpLandingJob(
            storage=FakeStorage(bucket),
            bigquery=FakeBigQuery(),
            bucket="raw-bucket",
            object_name="incoming/events.ndjson",
            raw_table=" ",
            quality_table="project.ops.issues",
        )
