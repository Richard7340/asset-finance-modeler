#!/usr/bin/env python
"""Siembra una cartera demo creíble en la base de datos del servidor.

Objetivo: que un fondo / family office que abra la plataforma vea una cartera
de ejemplo profesional y sensata, sin tener que construir nada a mano:

  * Activos OPERATIVOS (promovidos en el ciclo de vida, base bloqueada) con
    varios años de REALES introducidos, de modo que /variance y /live muestren
    una evolución real frente al plan. Uno va por encima del plan y otro por
    debajo, para que la desviación (y una alerta) sean demostrables.
  * OPORTUNIDADES (guardadas, sin promover) para la sección de valoración.
  * Nombres y ubicaciones (lat/lon) realistas para que el mapa tenga marcadores.

Usa los mismos stores y la misma resolución de ruta de BD que el servidor web
(``ASSET_FINANCE_DB_PATH`` o el valor por defecto), así que la cartera sembrada
es exactamente la que verá la API.

Es IDEMPOTENTE: cada activo usa un id estable (``scn-demo-*``) y se reescribe
(upsert) en cada ejecución; los reales de cada activo se borran y se vuelven a
insertar, de modo que volver a ejecutarlo no duplica nada.

Uso:
    ASSET_FINANCE_DB_PATH=/ruta/al/dir .venv/bin/python scripts/seed_demo.py
    # o, contra una BD demo fresca:
    ASSET_FINANCE_DB_PATH=$(mktemp -d) PYTHONPATH=src .venv/bin/python scripts/seed_demo.py
"""
from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Permite ejecutar el script directamente sin instalar el paquete (PYTHONPATH=src).
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Las descargas de embeddings no son necesarias para sembrar; evita que el
# import de la capa de inteligencia bloquee la siembra si no hay red.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from asset_finance_modeler.core.scenario import Scenario  # noqa: E402
from asset_finance_modeler.store.actuals import Actual, SQLiteActualsStore  # noqa: E402
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore  # noqa: E402
from asset_finance_modeler.web_api.assets import _db_path, _run_model  # noqa: E402

# Año de puesta en marcha de los activos operativos: ~2 años atrás, de modo que
# /live considere 2 años transcurridos y los reales de 2 ejercicios se solapen.
_COD = datetime(datetime.now(UTC).year - 2, 4, 1, tzinfo=UTC)
_COD_YEAR = _COD.year


def _save_asset(
    store: SQLiteScenarioStore,
    *,
    asset_id: str,
    model_id: str,
    name: str,
    location: str,
    lat: float,
    lon: float,
    tags: list[str],
    lifecycle: str,
) -> Scenario:
    """Crea (o reescribe) un activo demo con un id estable. Re-corre el modelo
    para congelar un ``results_snapshot`` coherente con los presets actuales."""
    results = _run_model(model_id, {})
    scenario = Scenario(
        id=asset_id,
        name=name,
        base_model=model_id,
        overrides={},
        inputs_snapshot={
            "model_id": model_id,
            "overrides": {},
            "location": location,
            "lat": lat,
            "lon": lon,
        },
        results_snapshot=results,
        tags=tags,
        lifecycle=lifecycle,
    )
    if lifecycle == "operational":
        scenario.base_locked = True
        scenario.is_canonical = True
        scenario.tracking_frequency = "monthly"
        scenario.commissioning_date = _COD
    store.save(scenario)
    return scenario


def _reset_actuals(actuals: SQLiteActualsStore, scenario_id: str) -> None:
    """Borra todos los reales previos de un activo (idempotencia)."""
    for a in actuals.list(scenario_id=scenario_id):
        actuals.delete(a.id)


def _seed_actuals_from_base(
    actuals: SQLiteActualsStore,
    scenario: Scenario,
    *,
    factors: list[float],
    lines: tuple[str, ...] = ("revenue", "ebitda", "net_income"),
) -> int:
    """Introduce reales para los primeros ``len(factors)`` ejercicios, derivados
    de la serie base congelada multiplicada por un factor por año (>1 = por
    encima del plan, <1 = por debajo). Devuelve cuántos reales se insertaron."""
    _reset_actuals(actuals, scenario.id)
    rows = (scenario.results_snapshot.get("income_statement") or {}).get("rows") or {}
    items: list[Actual] = []
    for year_offset, factor in enumerate(factors):
        period_start = f"{_COD_YEAR + year_offset}-01-01"
        for key in lines:
            series = rows.get(key)
            if not series or year_offset >= len(series):
                continue
            base_value = float(series[year_offset])
            items.append(
                Actual(
                    scenario_id=scenario.id,
                    period_start=period_start,
                    line_path=f"income_statement.rows.{key}",
                    value=round(base_value * factor, 2),
                    unit="EUR",
                    note=f"Real {_COD_YEAR + year_offset} (siembra demo)",
                )
            )
    if items:
        actuals.add_batch(items)
    return len(items)


def main() -> None:
    db_path = _db_path()
    store = SQLiteScenarioStore(db_path)
    store.initialize()
    actuals = SQLiteActualsStore(db_path)
    actuals.initialize()

    print(f"Sembrando cartera demo en: {db_path}\n")

    # --- OPERATIVOS (con reales) -------------------------------------------
    # Centro de datos: por ENCIMA del plan (+6% año 1, +9% año 2) → desviación
    # positiva, ideal para mostrar un activo que bate las previsiones.
    dc = _save_asset(
        store,
        asset_id="scn-demo-datacenter",
        model_id="datacenter_10mw_tier3",
        name="Data Center Tier-3 Madrid (10 MW IT)",
        location="Madrid, España",
        lat=40.4168,
        lon=-3.7038,
        tags=["demo", "infraestructura", "data_center"],
        lifecycle="operational",
    )
    n_dc = _seed_actuals_from_base(actuals, dc, factors=[1.06, 1.09])

    # Inmueble en alquiler: por DEBAJO del plan (-6% año 1, -5% año 2) → genera
    # una desviación negativa y una alerta demostrable.
    re = _save_asset(
        store,
        asset_id="scn-demo-realestate",
        model_id="real_estate_rental",
        name="Edificio residencial en alquiler — Valencia",
        location="Valencia, España",
        lat=39.4699,
        lon=-0.3763,
        tags=["demo", "inmobiliario"],
        lifecycle="operational",
    )
    n_re = _seed_actuals_from_base(actuals, re, factors=[0.94, 0.95])

    # Planta industrial: prácticamente EN plan (ligeramente por encima) → un
    # tercer activo operativo con seguimiento estable.
    ind = _save_asset(
        store,
        asset_id="scn-demo-industrial",
        model_id="business_industrial",
        name="Planta industrial — Zaragoza",
        location="Zaragoza, España",
        lat=41.6488,
        lon=-0.8891,
        tags=["demo", "negocio", "industrial"],
        lifecycle="operational",
    )
    n_ind = _seed_actuals_from_base(actuals, ind, factors=[1.01, 1.02])

    # --- OPORTUNIDADES (sin promover) --------------------------------------
    opportunities = [
        dict(
            asset_id="scn-demo-solar",
            model_id="solar_pv_50mw_spain",
            name="Planta solar FV 50 MWp — referencia",
            location="referencia, España",
            lat=37.8882,
            lon=-4.7794,
            tags=["demo", "infraestructura", "solar"],
        ),
        dict(
            asset_id="scn-demo-wind",
            model_id="wind_onshore_30mw_spain",
            name="Parque eólico 30 MW — Albacete",
            location="Albacete, España",
            lat=38.9943,
            lon=-1.8585,
            tags=["demo", "infraestructura", "eolica"],
        ),
        dict(
            asset_id="scn-demo-bess",
            model_id="bess_20mw_4h",
            name="Batería BESS 20 MW / 4h — Sevilla",
            location="Sevilla, España",
            lat=37.3891,
            lon=-5.9845,
            tags=["demo", "infraestructura", "bess"],
        ),
    ]
    for opp in opportunities:
        _save_asset(store, lifecycle="opportunity", **opp)

    # --- Resumen ------------------------------------------------------------
    print("Operativos (con reales):")
    print(f"  - {dc.name}  [+plan]  ({n_dc} reales)")
    print(f"  - {re.name}  [-plan]  ({n_re} reales)")
    print(f"  - {ind.name}  [~plan]  ({n_ind} reales)")
    print("\nOportunidades:")
    for opp in opportunities:
        print(f"  - {opp['name']}")
    total = len(store.list())
    print(f"\nTotal de activos en la cartera demo: {total}")


if __name__ == "__main__":
    main()
