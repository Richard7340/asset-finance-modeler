"""Cuanto vale un activo HOY (26-sep): la misma valoracion para cualquier modelo.

Parte de lo que ya calcula el modelo (cuenta de resultados y caja por anio) y da:
  - Descuento de flujos libres SIN deuda (FCFF = caja de operaciones + inversion
    + intereses despues de impuestos), con valor final en perpetuidad (Gordon)
    para negocios que siguen, o sin el para activos con vida finita (una planta,
    un piso que se vende al final: su venta ya esta en los flujos).
  - Multiplo de mercado opcional (EV/EBITDA de comparables, p.ej. buscado en
    internet): el valor por la otra via.
  - Deuda neta: valor de la empresa -> valor para el dueño.
  - Sensibilidad: tasa +-2 puntos x crecimiento +-1 punto.
  - valor_empresa es lo que vale el activo por sus flujos, SIN la inversion de
    partida (la de un negocio en marcha ya esta hecha); van = ese valor menos
    la inversion (para decidir si hacerla).
Todo en la moneda del modelo, a fecha de inicio de la proyeccion.
"""
from __future__ import annotations

from typing import Any

# Negocios que siguen despues del horizonte (valor final en perpetuidad).
_PERPETUOS = ("business_", "saas_")


def _anual(serie: list[float], n: int) -> list[float]:
    """Por anio aunque venga por periodos (mensual/trimestral)."""
    serie = [float(x or 0) for x in (serie or [])]
    if not serie or len(serie) == n or n <= 0:
        return serie[:n] if n > 0 else serie
    paso = max(1, len(serie) // n)
    return [sum(serie[i * paso:(i + 1) * paso]) for i in range(n)]


def flujos_libres(result: dict[str, Any]) -> dict[str, list[float]]:
    """FCFF por anio, EBITDA y el tipo impositivo efectivo de cada anio."""
    cf = result.get("cash_flow") or {}
    rows = (result.get("income_statement") or {}).get("rows") or {}
    n = len(cf.get("years") or rows.get("ebitda") or [])
    cfo, cfi = _anual(cf.get("cfo") or [], n), _anual(cf.get("cfi") or [], n)
    ebitda = _anual(rows.get("ebitda") or [0.0] * n, n)
    intereses = [abs(x) for x in _anual(rows.get("interest_expense") or [0.0] * n, n)]
    tax, ebt = _anual(rows.get("tax") or [0.0] * n, n), _anual(rows.get("ebt") or [0.0] * n, n)
    t = [min(max(abs(tax[y]) / ebt[y], 0.0), 0.5) if ebt[y] > 0 else 0.0 for y in range(n)]
    fcff = [cfo[y] + cfi[y] + intereses[y] * (1 - t[y]) for y in range(n)]
    return {"fcff": fcff, "ebitda": ebitda, "tipo_efectivo": t, "cfi": cfi}


def inversion_inicial(cfi: list[float], capex_total: float) -> tuple[list[float], float]:
    """La inversion de partida: la de los primeros anios hasta llegar al 90 %
    del capex del modelo (va dentro de los flujos), o todo el capex en el
    momento 0 si el modelo la deja fuera (p.ej. la compra de un piso).
    Devuelve (inversion por anio dentro de los flujos, inversion en el momento 0)."""
    dentro = [0.0] * len(cfi)
    if capex_total <= 0:
        return dentro, 0.0
    acum = 0.0
    for y, x in enumerate(cfi):
        if x < 0:
            dentro[y] = -x
            acum += -x
        if acum >= 0.9 * capex_total:
            return dentro, 0.0
    return [0.0] * len(cfi), capex_total


def _eur(x: float) -> str:
    return f"{round(x):,} €".replace(",", ".")


def _dcf(fcff: list[float], tasa: float, g: float, perpetuo: bool) -> dict[str, float]:
    vp = sum(f / (1 + tasa) ** (y + 1) for y, f in enumerate(fcff))
    vt = 0.0
    if perpetuo and fcff and tasa > g:
        vt = fcff[-1] * (1 + g) / (tasa - g)
    vp_vt = vt / (1 + tasa) ** len(fcff) if fcff else 0.0
    return {"vp_flujos": vp, "valor_terminal": vt, "vp_valor_terminal": vp_vt, "valor_empresa": vp + vp_vt}


def valorar(
    result: dict[str, Any],
    *,
    model_id: str,
    tasa: float,
    crecimiento: float = 0.02,
    perpetuidad: bool | None = None,
    multiplo_ebitda: float | None = None,
    deuda_neta: float = 0.0,
    ebitda_referencia: float | None = None,
) -> dict[str, Any]:
    if tasa is None or tasa <= -0.99:
        raise ValueError("tasa-invalida: la tasa de descuento tiene que ser un numero (0.08 = 8 %)")
    perpetuo = perpetuidad if perpetuidad is not None else model_id.startswith(_PERPETUOS)
    f = flujos_libres(result)
    if not f["fcff"]:
        raise ValueError("sin-flujos: el modelo no da ningun anio completo; revisa la duracion (anios)")
    ebitda = f["ebitda"]
    capex_total = float((result.get("kpis") or {}).get("total_capex") or 0)
    inv_anios, inv_cero = inversion_inicial(f["cfi"], capex_total)
    # Lo que vale el activo: sus flujos SIN la inversion de partida (la de un
    # negocio en marcha ya esta hecha). El VAN es ese valor menos la inversion.
    fcff = [f["fcff"][y] + inv_anios[y] for y in range(len(f["fcff"]))]
    vp_inversion = inv_cero + sum(x / (1 + tasa) ** (y + 1) for y, x in enumerate(inv_anios))
    notas: list[str] = []
    if perpetuo and tasa <= crecimiento:
        notas.append("La tasa no supera al crecimiento: sin valor final (la perpetuidad no converge).")
    d = _dcf(fcff, tasa, crecimiento, perpetuo)
    ev_dcf = d["valor_empresa"]
    salida: dict[str, Any] = {
        "metodo": "descuento de flujos libres sin deuda" + (" + valor final en perpetuidad" if perpetuo else " (vida finita, sin valor final)"),
        "tasa_descuento": tasa,
        "crecimiento_final": crecimiento if perpetuo else None,
        "anios": len(fcff),
        "flujos_libres": [round(x) for x in fcff],
        "dcf": {k: round(v) for k, v in d.items()},
        "peso_valor_terminal": round(d["vp_valor_terminal"] / ev_dcf, 3) if ev_dcf else None,
        "deuda_neta": round(deuda_neta),
        "valor_empresa": round(ev_dcf),
        "valor_para_el_dueno": round(ev_dcf - deuda_neta),
        "inversion_inicial": round(sum(inv_anios) + inv_cero),
        "van": round(ev_dcf - vp_inversion),
    }
    # EBITDA de referencia: el del primer anio en marcha (no el de obra).
    base_ebitda = ebitda_referencia if ebitda_referencia is not None else next((e for e in ebitda if e > 0), 0.0)
    if base_ebitda:
        salida["ev_ebitda_implicito"] = round(ev_dcf / base_ebitda, 2)
    if multiplo_ebitda:
        ev_m = base_ebitda * multiplo_ebitda
        salida["multiplo"] = {
            "ebitda_referencia": round(base_ebitda), "multiplo": multiplo_ebitda,
            "valor_empresa": round(ev_m), "valor_para_el_dueno": round(ev_m - deuda_neta),
        }
        lo, hi = sorted([ev_dcf, ev_m])
        salida["rango_valor_empresa"] = [round(lo), round(hi)]
        salida["rango_para_el_dueno"] = [round(lo - deuda_neta), round(hi - deuda_neta)]
        if base_ebitda <= 0:
            notas.append("EBITDA de referencia negativo o cero: el multiplo no sirve para valorarlo.")
    # Sensibilidad: filas = tasa, columnas = crecimiento final.
    tasas = [round(tasa + x, 4) for x in (-0.02, -0.01, 0.0, 0.01, 0.02) if tasa + x > 0]
    gs = [round(crecimiento + x, 4) for x in (-0.01, 0.0, 0.01)] if perpetuo else [crecimiento]
    salida["sensibilidad"] = {
        "tasas": tasas, "crecimientos": gs if perpetuo else None,
        "valor_empresa": [[round(_dcf(fcff, r, g, perpetuo)["valor_empresa"]) for g in gs] for r in tasas],
    }
    van_modelo = (result.get("kpis") or {}).get("npv")
    if isinstance(van_modelo, (int, float)):
        salida["van_del_modelo"] = round(van_modelo)
        if van_modelo and abs(salida["van"] - van_modelo) > 0.05 * abs(van_modelo):
            notas.append(
                f"El VAN que da el propio modelo ({_eur(van_modelo)}) y este ({_eur(salida['van'])}) no coinciden: "
                "calculan los impuestos de distinta forma. Aquí se usan los que el modelo calcula año a año "
                "(con compensación de pérdidas), quitando el ahorro fiscal de los intereses de la deuda."
            )
    if not deuda_neta:
        notas.append("Sin deuda neta indicada: el valor para el dueño es el de la empresa (pásala si tiene préstamos o caja).")
    # Lo que explica el valor, para que nadie lo explique mal (27-sep: un
    # agente dijo "no descuenta impuestos", y si los descuenta).
    salida["impuestos_incluidos"] = True
    positivos = [x for x in fcff if x > 0]
    if len(positivos) >= 2 and positivos[0] > 0:
        crec = (positivos[-1] / positivos[0]) ** (1 / (len(positivos) - 1)) - 1
        salida["crecimiento_medio_flujos"] = round(crec, 4)
        if salida.get("ev_ebitda_implicito") and salida["ev_ebitda_implicito"] > 10 and crec > 0.05:
            notas.append(
                f"El valor sale alto frente a múltiplos de mercado sobre todo porque los flujos crecen un {crec * 100:.1f} % al año "
                f"(el último año es {positivos[-1] / positivos[0]:.1f} veces el primero) y el valor final parte del último año. "
                "Los impuestos ya están descontados."
            )
    if salida["peso_valor_terminal"] and salida["peso_valor_terminal"] > 0.75:
        notas.append("Más del 75 % del valor está en el valor final: depende mucho del crecimiento y de la tasa.")
    salida["notas"] = notas
    return salida
