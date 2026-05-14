import json
import subprocess
import sys


def _run_cli(*args, cwd):
    cmd = [sys.executable, "-m", "asset_finance_modeler.cli.main", *args]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd))


def test_cli_list_models(tmp_path):
    result = _run_cli("list-models", cwd=tmp_path)
    assert result.returncode == 0
    assert "gestnova" in result.stdout


def test_cli_run_baseline_prints_summary(tmp_path):
    result = _run_cli("run", "--preset", "gestnova", "--output", "summary", cwd=tmp_path)
    assert result.returncode == 0
    # stdout should be valid JSON summary
    data = json.loads(result.stdout)
    assert "revenue_y1" in data


def test_cli_run_with_override(tmp_path):
    result = _run_cli(
        "run", "--preset", "gestnova",
        "--override", "revenue.sources[0].pricing.per_unit_per_period=200",
        "--output", "summary",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    base_result = _run_cli("run", "--preset", "gestnova", "--output", "summary", cwd=tmp_path)
    base_data = json.loads(base_result.stdout)
    # Override should reduce revenue
    assert data["revenue_end_period"] < base_data["revenue_end_period"]


def test_cli_run_export_csv(tmp_path):
    out_file = tmp_path / "pnl.csv"
    result = _run_cli(
        "run", "--preset", "gestnova",
        "--export", f"csv:pnl:{out_file}",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert out_file.exists()
    assert "revenue" in out_file.read_text()
