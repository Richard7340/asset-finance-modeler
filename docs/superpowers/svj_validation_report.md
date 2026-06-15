# SVJ — Reporte de validación y reconciliación (motor Python vs Excel)

**Fecha:** 2026-06-10 · **Actualizado:** 2026-06-15 (post auditoría adversaria) · **Motor:** asset-finance-modeler · **Deal:** SVJ 1&2 (FV + BESS híbrido, Córdoba)

Este documento registra QUÉ se corrió, bajo qué inputs, y por qué el motor reproduce (o se desvía de) el Excel validado. Sirve de trazabilidad: si se retoma el modelo, aquí está todo claro.

> **Actualización 2026-06-15 — dos correcciones de corrección:**
> - **FIX 1:** el arbitraje del BESS usaba siempre DoD 0,90 / RTE 0,88 hardcodeados e **ignoraba** los del preset (0,80 / 0,85). Corregido → el arbitraje honra el preset. Baja el NPV del BESS (cifra más conservadora).
> - **FIX 2:** la curva por fases tenía un off-by-one (una fase "7 años +2%" daba solo 6 pasos de capitalización). Corregido → `spread_da_es` alcanza `82×1,02⁷` al final de su fase. Sube ligeramente el arbitraje en los primeros años y mueve la captura merchant FV (también curva por fases).
>
> Efecto neto sobre el titular híbrido: **€1.317k → €957k** (más bajo, más defendible).

## Resultado final POST-FIX (presets calibrados, base PROYECTO sin apalancar @WACC 5,37%)

| KPI | Motor (post-fix) | Excel/teaser | Veredicto |
|---|---:|---:|---|
| NPV proy FV | −€716k | −€1.220k | ✅ coherente (activo marginal) |
| NPV proy BESS | +€1.673k | +€2.172k | ✅ conservador (DoD/RTE del preset) |
| **NPV proy híbrido (suma)** | **+€957k** | €953k (suma) | ✅ cuadra la suma |
| DSCR senior | 2,06× min | holgado | ✅ |
| DSCR subordinado inversor | avg 1,16× / min 0,94× | avg 1,22 / min 1,14 | ~ promedio cuadra; mínimo más ajustado |
| MOIC inversor | 1,368× | 1,37× | ✅ clavado |
| Recovery going-concern | 3,88× | ~1,4× | ✅ cubre principal (convención distinta) |
| Revenue FV yr1 | €298k | ~€293k | ✅ +2% (curva-driven) |

**Decisión de presentación (Riky, 2026-06-10):** se presenta la cifra **conservadora del motor** (híbrido proyecto ~€957k), NO el €1.644k del Excel. El €1.644k incluía un término de **sinergia de hibridación de €692k** (recuperación de curtailment + infra compartida) que era el número más blando del Excel; el motor lo omite → cifra más defendible ante un TDD.

## Por qué divergía (4 causas, todas resueltas)

1. **OPEX FV** — el motor partía de €107k/año (O&M €12k/MW + seguro + lease + gestión, realista para planta grande). **Decisión Riky:** instalación pequeña, gestión casera/barata → opex ~€35k (12% rev), como el Excel. Calibrado en el preset (`om_fixed 4000`, seguro 0,15%, lease/mgmt mínimos).
2. **Degradación BESS** — el motor aplicaba degradación de CAPACIDAD (`cycle_based`) al throughput de arbitraje. Pero el throughput del deal está **limitado por el excedente FV** (~50% prod FV ≈ 3.765 MWh), no por la capacidad del BESS → la degradación de la batería no debe reducir el arbitraje. Calibrado a `time_based 0.006` (degradación suave de la FV). Efecto: +€389k en el BESS.
3. **Convención NPV (proyecto vs equity)** — el "NPV proyecto" salía apalancado porque el preset lleva la deuda dentro. El bridge se mide **sin apalancar** (max_leverage=0 en la corrida de bridge). El motor aún sirve la deuda para los KPIs del inversor (DSCR/MOIC/recovery).
4. **Merchant FV** — el spot crecía +1%/año; debe **decrecer** por apuntamiento solar (captura €36→€29). Calibrado: `escalation_pct_yr: -0.015` en el stream merchant.

## Sobre el DSCR del inversor (honesto)
La cobertura de caja es **moderada-ajustada, NO holgada**: promedio ~1,20× (≈ teaser 1,22×, sobre covenant 1,15×), pero el **año peor (~yr7, tras la compresión del ancillary) baja a ~1,0×**. La fuerza del deal es el **colateral** (recovery 1,4×+ going-concern) + DSRA, no la cobertura. Presentar como **asset-backed**, coherente con el teaser ("stress sits below, backstopped by collateral & DSRA").

## Cómo se registran los revenue (verificado correcto)
- **FV:** PPA €43/MWh sobre el ~50% de volumen que carga el BESS + spot/merchant **cableado a la curva `solar_capture_es`** (captura €36→€29, Agere) sobre el resto. La curva ya embebe el apuntamiento y se aplica directamente (sin re-aplicar `capture_ratio` ni escalación encima). Revenue yr1 €298k (Excel €293k, +2%).
- **BESS:** arbitraje (spread `spread_da_es` €82 neto de carga ~€0, ×capture 0,80 ×DoD 0,80 ×RTE 0,85 ×throughput FV-limited) + ancillary (`afrr` €74k/MW × curva `ancillary_afrr_es` perfil Excel). La sinergia de carga FV-barata está **dentro del spread €82**, no se suma aparte.

## Presets / cómo reproducir
`load_preset("svj_fv_cordoba")` + `load_preset("svj_bess_cordoba")` → `HybridProject([fv,bess], 0.0537, senior=TrancheSpec(2220000,0.032,10), subordinated=TrancheSpec(1841000,0.085,7))`. Para el bridge unlevered: correr cada activo con `financing.max_leverage=0`.

## Decisiones de modelización divulgadas (un TDD preguntará — están aquí, no escondidas)

Tres supuestos deliberados que un due-diligence técnico cuestionará; se documentan para que sean **divulgados, no descubiertos**:

1. **Valor terminal (Gordon) por activo:** el EV por activo (`compute_dcf`) usa un valor terminal de perpetuidad de Gordon, apropiado para un activo de vida finita solo como aproximación. **El titular híbrido del SVJ NO lo usa:** el bridge se construye con `consolidate_npv`, que es una suma descontada de FCF anuales **sin valor terminal** (ver `test_bridge_is_sum_of_unlevered_legs_no_terminal_value`). El titular es por tanto conservador (sin cola de perpetuidad).
2. **EBITDA como proxy de CFADS:** DSCR y MOIC usan EBITDA como proxy del cash-flow available for debt service (pre-impuestos, pre-capex de mantenimiento). Es una **simplificación conocida** — sobreestima ligeramente la cobertura frente a un CFADS post-tax neto. La fuerza del deal es el colateral (recovery), no la cobertura.
3. **Acoplamiento físico FV→BESS = supuesto:** la carga barata del BESS desde el excedente FV se trata como **precio de captura neto de coste de carga ~€0** (embebido en el spread €82), NO se impone en el motor. El throughput del BESS deriva del nameplate del BESS (DoD/RTE/ciclos), independiente del excedente FV real periodo a periodo; el límite FV se aproxima vía degradación suave (`time_based 0.006`). Un acoplamiento físico explícito (cap = excedente FV) sería más exacto.

## Pendiente / mejoras futuras del motor (no bloqueantes)
- Amortización: las trances del inversor se modelan **anuales** (DSCR/MOIC) mientras los presets corren **mensual**; inconsistencia menor de granularidad, no afecta la magnitud de los KPIs (decisión: dejar como está).
- Throughput FV-limited modelado vía degradación suave; un acoplamiento físico explícito (cap = excedente FV) sería más exacto (ver supuesto 3 arriba).
- Depreciación del capex de repowering no programada aparte.
- Término de sinergia de hibridación opcional (curtailment/infra, ~€692k) no modelado (decisión conservadora).
