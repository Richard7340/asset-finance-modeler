"""Inmueble en alquiler (y su compra y venta), modelo profesional (26-sep).

El preset de "negocio generico" no servia para una casa: no habia gastos de
compra, ni hipoteca por LTV, ni vacancia, ni IPC, ni IBI/comunidad/seguro por
separado, ni fiscalidad del alquiler, ni venta con plusvalia. Aqui si, con
las reglas espanolas (todas son hipotesis editables):

  Compra     precio + ITP (usada) o IVA+AJD (obra nueva) + notaria/registro/
             gestoria + agencia + reforma. El suelo no se amortiza.
  Hipoteca   LTV sobre el precio, tipo, plazo, comision de apertura; cuota
             francesa mensual (intereses y capital por ano).
  Alquiler   renta mensual, meses vacios al ano, subida anual (IPC), impagos.
  Gastos     IBI, comunidad, seguro(s), mantenimiento, gestion, otros; suben
             con el IPC. Cada uno por separado (para anotar lo real).
  Impuestos  particular: rendimiento neto (ingresos - gastos - intereses -
             amortizacion 3 % de la construccion) con su reduccion por
             vivienda (50 % por defecto, art. 23.2 LIRPF) al tipo marginal;
             sociedad: 25 % con compensacion de perdidas.
  Venta      al final del horizonte: revalorizacion anual, costes de venta,
             plusvalia municipal y el impuesto sobre la ganancia (base del
             ahorro del IRPF 2026 o Sociedades).

Devuelve lo mismo que los demas modelos (kpis, cuenta de resultados, caja,
lineas por separado) y ademas el detalle de compra, hipoteca y venta.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Compra(BaseModel):
    precio: float = 250_000
    obra_nueva: bool = False
    # Usada: ITP de la comunidad autonoma (6-10 %). Nueva: IVA 10 % + AJD.
    itp_pct: float = 0.06
    iva_obra_nueva_pct: float = 0.10
    ajd_pct: float = 0.015
    notaria_registro_gestoria: float = 2_500
    comision_agencia: float = 0
    reforma: float = 0
    # Parte del valor que es suelo (no se amortiza): la del recibo del IBI.
    valor_suelo_pct: float = 0.35


class Hipoteca(BaseModel):
    ltv: float = 0.70
    tipo_interes: float = 0.03
    plazo_anios: int = 25
    comision_apertura_pct: float = 0.0


class Alquiler(BaseModel):
    renta_mensual: float = 1_100
    meses_vacios_anio: float = 0.5
    subida_anual: float = 0.02
    impagos_pct: float = 0.0
    otros_ingresos_anuales: float = 0


class Gastos(BaseModel):
    ibi_anual: float = 600
    comunidad_mensual: float = 80
    seguro_hogar_anual: float = 250
    seguro_impago_pct_renta: float = 0.0
    mantenimiento_pct_renta: float = 0.05
    gestion_pct_renta: float = 0.0
    otros_anuales: float = 0
    subida_anual: float = 0.02


class Impuestos(BaseModel):
    # "particular" (IRPF) o "sociedad" (Impuesto sobre Sociedades).
    regimen: str = "particular"
    tipo_marginal_irpf: float = 0.30
    # Reduccion del rendimiento neto positivo por alquiler de vivienda
    # (art. 23.2 LIRPF, Ley 12/2023): 50 % general; 60, 70 o 90 % en casos.
    reduccion_vivienda_pct: float = 0.50
    tipo_sociedades: float = 0.25
    amortizacion_pct: float = 0.03


class Venta(BaseModel):
    vender: bool = True
    revalorizacion_anual: float = 0.02
    costes_venta_pct: float = 0.03
    plusvalia_municipal: float = 0


class Inflacion(BaseModel):
    """IPC anio a anio (26-sep): sustituye a la subida anual de la renta y/o de
    los gastos (la renta de vivienda se actualiza por el indice que diga el
    contrato; aqui, la curva que ponga el usuario)."""

    curva: list[float] = Field(min_length=1)
    aplicar_a: Literal["todo", "ingresos", "gastos"] = "todo"


class Valoracion(BaseModel):
    tasa_descuento: float = 0.06


class InmuebleConfig(BaseModel):
    nombre: str = "Inmueble en alquiler"
    horizonte_anios: int = Field(10, ge=1, le=50)
    compra: Compra = Field(default_factory=Compra)
    hipoteca: Hipoteca = Field(default_factory=Hipoteca)
    alquiler: Alquiler = Field(default_factory=Alquiler)
    gastos: Gastos = Field(default_factory=Gastos)
    impuestos: Impuestos = Field(default_factory=Impuestos)
    venta: Venta = Field(default_factory=Venta)
    valoracion: Valoracion = Field(default_factory=Valoracion)
    inflacion: Inflacion | None = None


# Base del ahorro del IRPF 2026 (estatal + autonomica): la ganancia al vender.
TRAMOS_AHORRO = [(6_000, 0.19), (50_000, 0.21), (200_000, 0.23), (300_000, 0.27), (float("inf"), 0.30)]


def impuesto_ahorro(ganancia: float) -> float:
    if ganancia <= 0:
        return 0.0
    total, desde = 0.0, 0.0
    for hasta, tipo in TRAMOS_AHORRO:
        tramo = min(ganancia, hasta) - desde
        if tramo <= 0:
            break
        total += tramo * tipo
        desde = hasta
    return total


def tir(flujos: list[float]) -> float | None:
    """TIR por biseccion (robusta con cambios de signo raros). None si no hay."""
    if not any(f < 0 for f in flujos) or not any(f > 0 for f in flujos):
        return None
    def van(r: float) -> float:
        return sum(f / (1 + r) ** t for t, f in enumerate(flujos))
    lo, hi = -0.99, 10.0
    if van(lo) * van(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if van(lo) * van(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return round((lo + hi) / 2, 6)


def _hipoteca_anual(principal: float, tipo: float, plazo: int, anios: int) -> tuple[list[float], list[float], list[float], float]:
    """Cuota francesa mensual → intereses, capital y saldo al final de cada ano."""
    n = plazo * 12
    i = tipo / 12
    cuota = principal / n if i == 0 else principal * i / (1 - (1 + i) ** -n) if principal > 0 else 0.0
    saldo = principal
    intereses, capital, saldos = [], [], []
    for _y in range(anios):
        iy = cy = 0.0
        for _m in range(12):
            if saldo <= 0.005:
                break
            im = saldo * i
            cm = min(cuota - im, saldo)
            saldo -= cm
            iy += im
            cy += cm
        intereses.append(iy)
        capital.append(cy)
        saldos.append(max(saldo, 0.0))
    return intereses, capital, saldos, cuota


def ejecutar(cfg: InmuebleConfig) -> dict[str, Any]:
    c, h, a, g, t, v = cfg.compra, cfg.hipoteca, cfg.alquiler, cfg.gastos, cfg.impuestos, cfg.venta
    n = cfg.horizonte_anios
    anios = list(range(1, n + 1))

    # --- Compra -------------------------------------------------------------
    if c.obra_nueva:
        impuestos_compra = c.precio * (c.iva_obra_nueva_pct + c.ajd_pct)
        detalle_impuestos = {"IVA": round(c.precio * c.iva_obra_nueva_pct), "AJD": round(c.precio * c.ajd_pct)}
    else:
        impuestos_compra = c.precio * c.itp_pct
        detalle_impuestos = {"ITP": round(impuestos_compra)}
    prestamo = c.precio * h.ltv
    comision_apertura = prestamo * h.comision_apertura_pct
    gastos_compra = impuestos_compra + c.notaria_registro_gestoria + c.comision_agencia + comision_apertura
    inversion_total = c.precio + gastos_compra + c.reforma
    fondos_propios = inversion_total - prestamo
    # Lo amortizable: la construccion (sin suelo) con su parte de gastos, y la reforma.
    amortizable = (c.precio + gastos_compra - comision_apertura) * (1 - c.valor_suelo_pct) + c.reforma
    amortizacion = amortizable * t.amortizacion_pct

    # --- Hipoteca -------------------------------------------------------------
    intereses, capital, saldos, cuota = _hipoteca_anual(prestamo, h.tipo_interes, h.plazo_anios, n)

    # --- Ingresos y gastos por ano --------------------------------------------
    rentas, vacancia, impagos, otros_ing = [], [], [], []
    lineas_gastos: dict[str, list[float]] = {"IBI": [], "Comunidad": [], "Seguro del hogar": [], "Mantenimiento": []}
    if g.seguro_impago_pct_renta:
        lineas_gastos["Seguro de impago"] = []
    if g.gestion_pct_renta:
        lineas_gastos["Gestión"] = []
    if g.otros_anuales:
        lineas_gastos["Otros gastos"] = []
    from asset_finance_modeler.assets.business.engines import indice_ipc

    inf = cfg.inflacion
    idx = indice_ipc(inf.curva, n) if inf else None
    sube_renta = (lambda y: idx[y]) if idx and inf.aplicar_a in ("todo", "ingresos") else (lambda y: (1 + a.subida_anual) ** y)
    sube_gasto = (lambda y: idx[y]) if idx and inf.aplicar_a in ("todo", "gastos") else (lambda y: (1 + g.subida_anual) ** y)
    for y in range(n):
        bruta = a.renta_mensual * 12 * sube_renta(y)
        vac = bruta * min(a.meses_vacios_anio, 12) / 12
        cobrada = bruta - vac
        imp = cobrada * a.impagos_pct
        rentas.append(cobrada - imp)
        vacancia.append(vac)
        impagos.append(imp)
        otros_ing.append(a.otros_ingresos_anuales * sube_renta(y))
        f = sube_gasto(y)
        lineas_gastos["IBI"].append(g.ibi_anual * f)
        lineas_gastos["Comunidad"].append(g.comunidad_mensual * 12 * f)
        lineas_gastos["Seguro del hogar"].append(g.seguro_hogar_anual * f)
        lineas_gastos["Mantenimiento"].append(bruta * g.mantenimiento_pct_renta)
        if "Seguro de impago" in lineas_gastos:
            lineas_gastos["Seguro de impago"].append(bruta * g.seguro_impago_pct_renta)
        if "Gestión" in lineas_gastos:
            lineas_gastos["Gestión"].append(cobrada * g.gestion_pct_renta)
        if "Otros gastos" in lineas_gastos:
            lineas_gastos["Otros gastos"].append(g.otros_anuales * f)
    ingresos = [rentas[y] + otros_ing[y] for y in range(n)]
    gastos = [sum(l[y] for l in lineas_gastos.values()) for y in range(n)]
    noi = [ingresos[y] - gastos[y] for y in range(n)]  # resultado operativo (EBITDA)

    # --- Impuestos sobre el alquiler -------------------------------------------
    base = [noi[y] - intereses[y] - amortizacion for y in range(n)]
    impuesto: list[float] = []
    perdidas = 0.0
    for y in range(n):
        if t.regimen == "sociedad":
            b = base[y]
            if b > 0 and perdidas > 0:
                usado = min(b, perdidas); b -= usado; perdidas -= usado
            elif b < 0:
                perdidas += -b
            impuesto.append(max(b, 0.0) * t.tipo_sociedades)
        else:
            # Particular: reduccion por vivienda solo sobre el rendimiento POSITIVO.
            b = base[y] * (1 - t.reduccion_vivienda_pct) if base[y] > 0 else base[y]
            impuesto.append(max(b, 0.0) * t.tipo_marginal_irpf)
    neto = [base[y] - impuesto[y] for y in range(n)]

    # --- Venta -----------------------------------------------------------------
    precio_venta = c.precio * (1 + v.revalorizacion_anual) ** n if v.vender else 0.0
    costes_venta = precio_venta * v.costes_venta_pct + (v.plusvalia_municipal if v.vender else 0.0)
    valor_fiscal = c.precio + gastos_compra - comision_apertura + c.reforma - amortizacion * n
    ganancia = precio_venta - costes_venta - valor_fiscal if v.vender else 0.0
    imp_venta = (ganancia * t.tipo_sociedades if t.regimen == "sociedad" else impuesto_ahorro(ganancia)) if v.vender and ganancia > 0 else 0.0
    deuda_pendiente = saldos[-1] if saldos else 0.0

    # --- Caja --------------------------------------------------------------------
    cfo = [noi[y] - intereses[y] - impuesto[y] for y in range(n)]
    cfi = [0.0] * n
    cff = [-capital[y] for y in range(n)]
    if v.vender:
        cfi[-1] += precio_venta - costes_venta - imp_venta
        cff[-1] -= deuda_pendiente
    proyecto = [-inversion_total] + [noi[y] - (impuesto[y] if t.regimen == "sociedad" else impuesto[y]) for y in range(n)]
    if v.vender:
        proyecto[-1] += precio_venta - costes_venta - imp_venta
    accionista = [-fondos_propios] + [cfo[y] + cfi[y] + cff[y] for y in range(n)]
    tasa = cfg.valoracion.tasa_descuento
    # Como en el resto de modelos: el VAN es el del PROYECTO (sin hipoteca); el
    # del accionista, aparte (npv_equity).
    van = sum(f / (1 + tasa) ** i for i, f in enumerate(proyecto))
    van_accionista = sum(f / (1 + tasa) ** i for i, f in enumerate(accionista))
    servicio_deuda = [intereses[y] + capital[y] for y in range(n)]
    dscr = [noi[y] / servicio_deuda[y] for y in range(n) if servicio_deuda[y] > 0]
    acumulado, payback = -fondos_propios, None
    for y in range(n):
        acumulado += accionista[y + 1]
        if payback is None and acumulado >= 0:
            payback = y + 1

    r0 = lambda xs: [round(x) for x in xs]  # noqa: E731
    # La hipoteca año a año y la caja acumulada (28-sep), para la app.
    saldo, vivo = [], prestamo
    for y in range(n):
        vivo = max(vivo - capital[y], 0.0)
        saldo.append(vivo)
    caja, acc = [], 0.0
    for y in range(n):
        acc += cfo[y] + cfi[y] + cff[y]
        caja.append(acc)
    return {
        "kpis": {
            "npv": round(van),
            "npv_equity": round(van_accionista),
            "irr_project": tir(proyecto),
            "irr_equity": tir(accionista),
            "dscr_min": round(min(dscr), 2) if dscr else None,
            "total_capex": round(inversion_total),
            "rentabilidad_bruta": round(a.renta_mensual * 12 / c.precio, 4) if c.precio else None,
            "rentabilidad_neta": round(noi[0] / inversion_total, 4) if inversion_total else None,
            "cash_on_cash_y1": round(accionista[1] / fondos_propios, 4) if fondos_propios > 0 else None,
            "payback_anios": payback,
            "payback_years": payback,
            "fondos_propios": round(fondos_propios),
            "cuota_hipoteca_mensual": round(cuota, 2),
        },
        "income_statement": {"years": anios, "rows": {
            "revenue": r0(ingresos), "ebitda": r0(noi), "ebit": r0([noi[y] - amortizacion for y in range(n)]),
            "interest_expense": r0(intereses), "ebt": r0(base), "tax": r0(impuesto), "net_income": r0(neto),
        }},
        "cash_flow": {"years": anios, "cfo": r0(cfo), "cfi": r0(cfi), "cff": r0(cff), "cash": r0(caja)},
        **({"deuda": {"years": anios, "saldo": r0(saldo), "intereses": r0(intereses), "amortizacion": r0(capital),
                      "disposiciones": [round(prestamo)] + [0] * (n - 1),
                      "dscr": [round(noi[y] / servicio_deuda[y], 2) if servicio_deuda[y] > 0 else None for y in range(n)]}} if prestamo > 0 else {}),
        "lineas": {
            "ingresos": {"Rentas": r0(rentas), **({"Otros ingresos": r0(otros_ing)} if a.otros_ingresos_anuales else {})},
            "gastos": {k: r0(vs) for k, vs in lineas_gastos.items()},
        },
        "detalle": {
            "compra": {"precio": round(c.precio), **detalle_impuestos, "notaria_registro_gestoria": round(c.notaria_registro_gestoria),
                       "agencia": round(c.comision_agencia), "comision_apertura": round(comision_apertura), "reforma": round(c.reforma),
                       "gastos_de_compra": round(gastos_compra), "inversion_total": round(inversion_total)},
            "hipoteca": {"prestamo": round(prestamo), "cuota_mensual": round(cuota, 2), "intereses_totales": round(sum(intereses)),
                         "pendiente_al_final": round(deuda_pendiente)},
            "alquiler": {"vacancia_anual": r0(vacancia), "impagos_anuales": r0(impagos)},
            "amortizacion_anual": round(amortizacion),
            "venta": ({"anio": n, "precio": round(precio_venta), "costes": round(costes_venta), "ganancia": round(ganancia),
                       "impuesto": round(imp_venta), "neto_para_el_propietario": round(precio_venta - costes_venta - imp_venta - deuda_pendiente)}
                      if v.vender else None),
            "flujos_accionista": r0(accionista),
            "flujos_proyecto": r0(proyecto),
        },
        "summary": {"model": "inmueble", "horizon_years": n, "regimen_fiscal": t.regimen},
    }
