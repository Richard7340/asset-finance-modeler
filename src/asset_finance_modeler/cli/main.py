"""Thin CLI for asset-finance-modeler.

Examples:
    python -m asset_finance_modeler.cli.main list-models
    python -m asset_finance_modeler.cli.main run --preset gestnova --output summary
    python -m asset_finance_modeler.cli.main run --preset gestnova \\
        --override revenue.sources[0].pricing.per_unit_per_period=200 \\
        --export xlsx::./out.xlsx --export csv:pnl:./pnl.csv
"""
import argparse
import json
import sys

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id, run_scenario_saas
from asset_finance_modeler.store.exports import (
    to_csv,
    to_json,
    to_markdown_report,
    to_markdown_table,
    to_summary,
    to_xlsx,
)

_AVAILABLE_PRESETS = ["gestnova"]
_EXPORT_PARTS_COUNT = 3


def _parse_override(spec: str) -> tuple[str, object]:
    if "=" not in spec:
        raise ValueError(f"Bad override (need key=value): {spec!r}")
    key, raw_value = spec.split("=", 1)
    # Try numeric, fall back to string
    try:
        value: object = int(raw_value)
    except ValueError:
        try:
            value = float(raw_value)
        except ValueError:
            value = raw_value
    return key.strip(), value


def _do_list_models() -> int:
    for name in _AVAILABLE_PRESETS:
        print(name)
    return 0


def _do_run(args: argparse.Namespace) -> int:
    overrides = {}
    for spec in args.override or []:
        k, v = _parse_override(spec)
        overrides[k] = v

    scenario = Scenario(
        id=new_scenario_id(),
        name=args.name or "cli-run",
        base_model=args.preset,
        overrides=overrides,
    )
    results = run_scenario_saas(scenario)

    # Print primary output
    if args.output == "summary":
        print(json.dumps(to_summary(results), default=str, indent=2))
    elif args.output == "json":
        print(to_json(results))
    elif args.output in ("pnl", "cashflow", "balance", "unit_econ"):
        print(to_markdown_table(results, view=args.output))
    elif args.output == "report":
        print(to_markdown_report(results))
    else:
        raise ValueError(f"Unknown --output: {args.output}")

    # Optional exports
    for export_spec in args.export or []:
        # Format: "csv:view:path" or "xlsx::path" or "json::path"
        parts = export_spec.split(":", 2)
        if len(parts) != _EXPORT_PARTS_COUNT:
            raise ValueError(f"Bad --export (expected fmt:view:path): {export_spec!r}")
        fmt, view, path = parts
        if fmt == "csv":
            to_csv(results, view=view, path=path)
        elif fmt == "xlsx":
            to_xlsx(results, path=path)
        elif fmt == "json":
            to_json(results, path=path)
        else:
            raise ValueError(f"Unknown export fmt: {fmt!r}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="asset-finance-modeler")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-models")

    run_p = sub.add_parser("run")
    run_p.add_argument("--preset", required=True)
    run_p.add_argument("--name", default=None)
    run_p.add_argument("--override", action="append", default=[])
    run_p.add_argument("--output", default="summary",
                       choices=["summary", "json", "report", "pnl", "cashflow", "balance", "unit_econ"])
    run_p.add_argument("--export", action="append", default=[])

    args = parser.parse_args(argv)

    if args.cmd == "list-models":
        return _do_list_models()
    if args.cmd == "run":
        return _do_run(args)
    parser.error(f"Unknown command: {args.cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
