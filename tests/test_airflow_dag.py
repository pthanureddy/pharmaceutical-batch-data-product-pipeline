import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("airflow")


def test_composer_dag_loads_with_retries_and_ordered_quality_gate():
    dag_path = Path(__file__).parents[1] / "orchestration" / "dags" / "batch_data_product.py"
    spec = importlib.util.spec_from_file_location("batch_data_product", dag_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dag = module.dag

    assert dag.schedule_interval == "*/15 * * * *"
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert set(dag.task_ids) == {
        "execute_ingest_job",
        "merge_batch_snapshot",
        "check_data_quality",
    }
    assert all(task.retries == 3 for task in dag.tasks)
    assert dag.get_task("execute_ingest_job").downstream_task_ids == {"merge_batch_snapshot"}
    assert dag.get_task("merge_batch_snapshot").downstream_task_ids == {"check_data_quality"}
    assert "gcloud run jobs execute" in dag.get_task("execute_ingest_job").bash_command
    assert "002_incremental_batch_snapshot.sql" in dag.get_task("merge_batch_snapshot").bash_command
