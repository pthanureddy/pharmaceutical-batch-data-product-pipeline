import json

from pharma_data_product.cli import main
from tests.test_models import valid_event


def test_cli_init_ingest_and_summary(tmp_path, capsys):
    database = tmp_path / "data.db"
    source = tmp_path / "events.ndjson"
    source.write_text(json.dumps(valid_event()) + "\n", encoding="utf-8")

    assert main(["init", "--database", str(database)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ready"

    assert main(["ingest", "--database", str(database), "--input", str(source)]) == 0
    assert json.loads(capsys.readouterr().out)["accepted_count"] == 1

    assert main(["summary", "--database", str(database)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["raw_event_count"] == 1
    assert summary["batch_count"] == 1
    assert summary["latest_run"]["accepted_count"] == 1


def test_cli_returns_two_when_quarantine_occurs(tmp_path, capsys):
    source = tmp_path / "events.ndjson"
    source.write_text("not-json\n", encoding="utf-8")
    code = main(
        [
            "ingest",
            "--database",
            str(tmp_path / "data.db"),
            "--input",
            str(source),
        ]
    )
    assert code == 2
    assert json.loads(capsys.readouterr().out)["quarantined_count"] == 1

