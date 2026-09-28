"""MCP tools finance.track.* — implementacion real sobre SQLiteActualsStore.

Sustituye a make_track_stub: importar actuals, conciliar base vs real y
varianza por linea. Reutiliza los helpers de web_api.actuals (la misma
matematica del panel): nada se duplica, nada se inventa (anos sin dato
quedan None).
"""
from __future__ import annotations

from typing import Any

from asset_finance_modeler.store.actuals import Actual, SQLiteActualsStore
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore
from asset_finance_modeler.web_api.actuals import (
    _trackable_lines,
    _variance_for_line,
)


def _stores(
    store: SQLiteScenarioStore,
) -> tuple[SQLiteScenarioStore, SQLiteActualsStore]:
    """El store de escenarios que nos inyectan + actuals del mismo entorno.

    En el servidor HTTP ambos cuelgan del mismo _db_path() (misma env
    ASSET_FINANCE_DB_PATH que el volumen); en tests se usa el que haya.
    """
    # Misma base que escenarios (asset_actuals convive con scenarios en un
    # SQLite). A proposito NO se usa el _db_path() global: en tests y en
    # despliegues con ruta propia, el store inyectado es la unica verdad.
    actuals = SQLiteActualsStore(str(store.db_path))
    actuals.initialize()
    return store, actuals


def _get(store: SQLiteScenarioStore, args: dict[str, Any]) -> Any:
    s = store.get(args["scenario_id"], workspace_id=args.get("workspace_id"))
    if (s is None or s.is_deleted) and not str(args["scenario_id"]).startswith("scn-"):
        # Por su nombre (27-sep: los agentes lo piden asi), si encaja uno solo.
        import re
        import unicodedata

        def plano(x: Any) -> str:
            t = unicodedata.normalize("NFD", str(x or "").lower())
            t = "".join(c for c in t if unicodedata.category(c) != "Mn")
            return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())

        pedido = plano(args["scenario_id"])
        todos = [x for x in store.list(workspace_id=args.get("workspace_id")) if not x.is_deleted]
        iguales = [x for x in todos if plano(x.name) == pedido] or [x for x in todos if pedido and pedido in plano(x.name)]
        s = iguales[0] if len(iguales) == 1 else None
    if s is None or s.is_deleted:
        return None
    return s


def make_track_import(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        s = _get(store, args)
        if s is None:
            return {"error": f"scenario_id {args.get('scenario_id')!r} not found"}
        brutos = args.get("actuals")
        if not isinstance(brutos, list) or not brutos:
            return {"error": "actuals-required: [{line_path, period_start, value}]"}
        _, actuals = _stores(store)
        # Solo lineas que existen en el activo (26-sep: un "IBI" mal escrito se
        # guardaba y no se comparaba con nada). Por nombre tambien vale:
        # "IBI" -> lineas.gastos.IBI si es la unica que encaja.
        validas = [ln["path"] for ln in _trackable_lines(s.results_snapshot or {})]

        def resolver(lp: str) -> str | None:
            if not validas or lp in validas:
                return lp
            k = lp.strip().lower()
            cand = [v for v in validas if v.lower().endswith("." + k) or v.split(".")[-1].lower() == k]
            if not cand:
                # "IBI" -> "lineas.gastos.Comunidad+IBI+seguros" si es la unica que lo contiene.
                cand = [v for v in validas if v.startswith("lineas.") and k in v.split(".", 2)[-1].lower()]
            return cand[0] if len(cand) == 1 else None

        nuevos: list[Actual] = []
        for i, b in enumerate(brutos):
            if not isinstance(b, dict) or not b.get("line_path") or not b.get("period_start"):
                return {"error": f"actuals[{i}] needs line_path + period_start"}
            lp = resolver(str(b["line_path"]))
            if lp is None:
                return {"error": "unknown-line", "detail": f"actuals[{i}].line_path {b['line_path']!r} no es una linea de este activo", "lineas": validas}
            b = {**b, "line_path": lp}
            try:
                value = float(b.get("value"))
            except (TypeError, ValueError):
                return {"error": f"actuals[{i}].value must be a number"}
            nuevos.append(Actual(
                scenario_id=s.id,
                period_start=str(b["period_start"]),
                line_path=str(b["line_path"]),
                value=value,
                unit=str(b.get("unit", "")),
                note=str(b.get("note", "")),
            ))
        ids = actuals.add_batch(nuevos)
        from asset_finance_modeler.web_api.assets import en_operacion_si_tiene_reales  # noqa: PLC0415

        paso = en_operacion_si_tiene_reales(store, s, [n.period_start for n in nuevos])
        return {"ok": True, "scenario_id": s.id, "imported": ids,
                **({"pasado_a_operacion": True, "nota": "Tenia datos reales: ahora esta en la Cartera (en operacion)."} if paso else {})}
    return _handle


def make_track_reconcile(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        s = _get(store, args)
        if s is None:
            return {"error": f"scenario_id {args.get('scenario_id')!r} not found"}
        if not s.results_snapshot:
            return {"error": f"scenario {s.id!r} has no results — run it first"}
        _, actuals = _stores(store)
        filas = actuals.list(s.id)
        lineas = []
        for ln in _trackable_lines(s.results_snapshot):
            lp = ln["path"]
            vals = [a.value for a in filas if a.line_path == lp]
            lineas.append({
                "line_path": lp,
                "label": ln.get("label"),
                "n_actuals": len(vals),
                "actual_total": round(sum(vals), 4) if vals else None,
            })
        return {
            "scenario_id": s.id,
            "n_actuals": len(filas),
            "lines": lineas,
        }
    return _handle


def make_track_variance(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        s = _get(store, args)
        if s is None:
            return {"error": f"scenario_id {args.get('scenario_id')!r} not found"}
        if not s.results_snapshot:
            return {"error": f"scenario {s.id!r} has no results — run it first"}
        _, actuals = _stores(store)
        filas = actuals.list(s.id)
        lineas = _trackable_lines(s.results_snapshot)
        solo = args.get("line_path")
        if solo:
            lineas = [ln for ln in lineas if ln["path"] == solo]
            if not lineas:
                return {"error": f"line_path {solo!r} not trackable here"}
        return {
            "scenario_id": s.id,
            "lines": [
                _variance_for_line(s, filas, ln["path"], ln.get("label", ""), ln.get("unit", ""))
                for ln in lineas
            ],
        }
    return _handle


__all__ = ["make_track_import", "make_track_reconcile", "make_track_variance"]


def make_track_lines(store: SQLiteScenarioStore) -> Any:
    """Las lineas de un activo contra las que se anota lo real (ingresos y
    gastos por separado, EBITDA, caja…)."""
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        s = _get(store, args)
        if s is None:
            return {"error": f"scenario_id {args.get('scenario_id')!r} not found"}
        return {"scenario_id": s.id, "lineas": _trackable_lines(s.results_snapshot or {})}
    return _handle
