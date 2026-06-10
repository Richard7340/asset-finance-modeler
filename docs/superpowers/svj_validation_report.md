# SVJ — Reporte de validación y reconciliación (motor Python vs Excel)

**Fecha:** 2026-06-10 · **Motor:** asset-finance-modeler · **Deal:** SVJ 1&2 (FV + BESS híbrido, Córdoba)

Este documento registra QUÉ se corrió, bajo qué inputs, y por qué el motor reproduce (o se desvía de) el Excel validado. Sirve de trazabilidad: si se retoma el modelo, aquí está todo claro.

## Resultado final (presets calibrados, base PROYECTO sin apalancar @WACC 5,37%)

| KPI | Motor (final) | Excel/teaser | Veredicto |
|---|---:|---:|---|
| NPV proy FV | −€999k | −€1.220k | ✅ coherente (activo marginal) |
| NPV proy BESS | +€2.031k | +€2.172k | ✅ −6% |
| **NPV proy híbrido (suma)** | **+€1.032k** | €953k (suma) | ✅ cuadra la suma |
| DSCR senior (FV) | 2,10× min | holgado | ✅ |
| DSCR subordinado inversor | avg 1,20× / min 0,98× | avg 1,22 / min 1,14 | ~ promedio cuadra; mínimo más fino |
| MOIC inversor | 1,37× | 1,37× | ✅ clavado |
| Recovery going-concern | 3,90× | ~1,4× | ✅ cubre principal (convención distinta) |

**Decisión de presentación (Riky, 2026-06-10):** se presenta la cifra **conservadora del motor** (híbrido proyecto ~€1.032k), NO el €1.644k del Excel. El €1.644k incluía un término de **sinergia de hibridación de €692k** (recuperación de curtailment + infra compartida) que era el número más blando del Excel; el motor lo omite → cifra más defendible ante un TDD.

## Por qué divergía (4 causas, todas resueltas)

1. **OPEX FV** — el motor partía de €107k/año (O&M €12k/MW + seguro + lease + gestión, realista para planta grande). **Decisión Riky:** instalación pequeña, gestión casera/barata → opex ~€35k (12% rev), como el Excel. Calibrado en el preset (`om_fixed 4000`, seguro 0,15%, lease/mgmt mínimos).
2. **Degradación BESS** — el motor aplicaba degradación de CAPACIDAD (`cycle_based`) al throughput de arbitraje. Pero el throughput del deal está **limitado por el excedente FV** (~50% prod FV ≈ 3.765 MWh), no por la capacidad del BESS → la degradación de la batería no debe reducir el arbitraje. Calibrado a `time_based 0.006` (degradación suave de la FV). Efecto: +€389k en el BESS.
3. **Convención NPV (proyecto vs equity)** — el "NPV proyecto" salía apalancado porque el preset lleva la deuda dentro. El bridge se mide **sin apalancar** (max_leverage=0 en la corrida de bridge). El motor aún sirve la deuda para los KPIs del inversor (DSCR/MOIC/recovery).
4. **Merchant FV** — el spot crecía +1%/año; debe **decrecer** por apuntamiento solar (captura €36→€29). Calibrado: `escalation_pct_yr: -0.015` en el stream merchant.

## Sobre el DSCR del inversor (honesto)
La cobertura de caja es **moderada-ajustada, NO holgada**: promedio ~1,20× (≈ teaser 1,22×, sobre covenant 1,15×), pero el **año peor (~yr7, tras la compresión del ancillary) baja a ~1,0×**. La fuerza del deal es el **colateral** (recovery 1,4×+ going-concern) + DSRA, no la cobertura. Presentar como **asset-backed**, coherente con el teaser ("stress sits below, backstopped by collateral & DSRA").

## Cómo se registran los revenue (verificado correcto)
- **FV:** PPA €43/MWh sobre el ~50% de volumen que carga el BESS + spot/merchant €36 (decreciente) sobre el resto. Revenue yr1 €278k (Excel €293k, −5%).
- **BESS:** arbitraje (spread `spread_da_es` €82 neto de carga ~€0, ×capture 0,80 ×throughput FV-limited) + ancillary (`afrr` €74k/MW × curva `ancillary_afrr_es` perfil Excel). Revenue yr1 €585k (Excel €582k ✅). La sinergia de carga FV-barata está **dentro del spread €82**, no se suma aparte.

## Presets / cómo reproducir
`load_preset("svj_fv_cordoba")` + `load_preset("svj_bess_cordoba")` → `HybridProject([fv,bess], 0.0537, senior=TrancheSpec(2220000,0.032,10), subordinated=TrancheSpec(1841000,0.085,7))`. Para el bridge unlevered: correr cada activo con `financing.max_leverage=0`.

## Pendiente / mejoras futuras del motor (no bloqueantes)
- DSCR usa EBITDA como proxy de CFADS (no post-tax neto). Refinamiento futuro.
- `MerchantStream.price_curve` declarado pero no usado por `_merchant` (se usó escalation negativa como proxy del apuntamiento; idealmente cablear la curva `solar_capture_es`).
- Throughput FV-limited modelado vía degradación suave; un acoplamiento físico explícito (cap = excedente FV) sería más exacto.
- Depreciación del capex de repowering no programada aparte.
- Término de sinergia de hibridación opcional (curtailment/infra) no modelado (decisión conservadora).
