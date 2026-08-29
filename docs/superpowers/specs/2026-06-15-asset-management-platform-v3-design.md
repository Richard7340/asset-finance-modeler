# Diseño — Plataforma de gestión integral de activos (v3)

**Fecha:** 2026-06-15 · **Autores:** Riky + Aurora · **Repo:** `asset-finance-modeler` · **Rama:** `feat/finance-engine-general-deals` · **Estado:** spec para revisión

## 1. Propósito

Evolucionar la plataforma (motor + 11 modelos + curvas + cartera + frontend IB-grade ya construidos en v1/v2) a una **plataforma de gestión integral de activos** para **fondos de inversión, bancos y family offices**. El usuario gestiona TODOS sus activos desde un único lugar, distinguiendo:

- **Activos EN OPERACIÓN** (cartera real): se gestionan **día a día** metiendo datos reales (producción, ingresos, costes, deuda, cualquier input de su modelo) y se ve la **desviación frente a lo que se fijó el día de la compra / puesta en operación**.
- **Oportunidades**: simulaciones / valoraciones de posibles compras o inversiones. NO cuentan como cartera; se valoran libremente y, al adquirirse, **se promueven a cartera** (se congela su caso base y empieza el seguimiento).

El objetivo es un producto **realmente incorporable** en un fondo/family office: control total del activo en el día a día, máxima versatilidad (cualquier tipo de activo, modelado a su manera), y una plataforma tan visual que cualquiera —profesional o no— entienda y gestione sus activos.

Construye sobre lo existente: `Scenario` store (SQLite, `inputs_snapshot`/`results_snapshot`, versionado por `parent_scenario_id`, `tags`, `is_canonical`, `user_id`, `workspace_id`), motor `InfrastructureModel`/`BusinessModel`→`FinancialOutput`, introspección `schema_tree`/`set_by_path`, API `/api/models|assets|portfolio|curves`, frontend React en `web/`.

## 2. Decisiones de diseño aprobadas

1. **Base inmutable + escenario LIVE derivado.** Cada activo operativo guarda su **BASE** congelado (el caso del día de adquisición / puesta en operación, lo comprometido). Los datos reales alimentan un escenario **LIVE** *derivado* (no se congela): sustituye los periodos ya ocurridos por lo real y reproyecta el futuro con los supuestos actuales (que también se pueden actualizar). Se muestran **BASE vs LIVE lado a lado** (VAN/TIR/desviación).
2. **Reales contra cualquier línea del propio modelo del activo.** No hay una lista fija de métricas. Cada activo se controla según SU estructura (cada empresa tiene sus costes/ingresos/deuda modelados a su manera). Los datos reales se registran contra **cualquier path del modelo de ese activo** (`production`, `revenue[0]`, una línea de opex, servicio de deuda, precio…), que el motor ya expone vía `schema_tree`. Frecuencia **configurable por activo** (diaria / mensual / trimestral).
3. **Dashboard que separa Cartera vs Oportunidades** (ver §4).
4. **Overlay por agregación para el LIVE.** El motor proyecta anual; los reales entran sub-anuales. El LIVE agrega los reales a la frecuencia del modelo (año en curso = reales acumulados + resto proyectado; años pasados = reales) para recalcular la valoración a nivel anual, mientras la **varianza se muestra a la granularidad fina**. (Reescribir el motor a multi-periodo nativo queda fuera de alcance — posible v4.)
5. **Construcción por fases** (ver §6).
6. **UI grado fondo/banco, máxima riqueza visual, SIN EMOJIS** (iconos lucide), look de sistema operativo financiero.

## 3. Modelo de datos (nuevo)

### 3.1 Ciclo de vida del activo
Añadir al `Scenario` (o tabla asociada) un estado de ciclo de vida:
- `lifecycle`: `"opportunity"` (por defecto) | `"operational"`.
- `commissioning_date`: fecha de puesta en operación / adquisición (se fija al promover; ancla del seguimiento). `NULL` para oportunidades.
- `base_locked`: bool — al promover a operación, el caso base queda inmutable (se versiona como `is_canonical` y futuras ediciones del LIVE no lo tocan).
- `tracking_frequency`: `"daily" | "monthly" | "quarterly"` (por activo, sólo operativos).

Migración SQLite **aditiva** (columnas nuevas con defaults) — no rompe filas existentes.

### 3.2 Serie temporal de datos reales — tabla `asset_actuals`
```
asset_actuals(
  id            TEXT PRIMARY KEY,
  scenario_id   TEXT NOT NULL,         -- el activo (Scenario) en operación
  period_start  TEXT NOT NULL,         -- fecha ISO del periodo (día/mes/trimestre)
  line_path     TEXT NOT NULL,         -- path del modelo: 'production', 'revenue[0]', 'opex.om', 'debt.senior.service'...
  value         REAL NOT NULL,
  unit          TEXT NOT NULL DEFAULT '',
  note          TEXT NOT NULL DEFAULT '',
  entered_by    TEXT NOT NULL DEFAULT 'default',
  entered_at    TEXT NOT NULL,
  FOREIGN KEY (scenario_id) REFERENCES scenarios(id)
)
INDEX (scenario_id, line_path, period_start)
```
Cada fila = un valor real para una línea del modelo en un periodo. Multi-tenant vía el `user_id`/`workspace_id` del `Scenario` padre.

### 3.3 Escenario LIVE (derivado, calculado)
No se persiste como fila propia (se puede materializar en cache/`results_snapshot` para el dashboard). Se calcula:
`LIVE = BASE.overrides + (actuals agregados a periodos pasados, por line_path) + supuestos futuros actuales`.
Produce un `FinancialOutput` LIVE comparable al BASE → VAN/TIR/cashflow live + desviación por línea/periodo.

## 4. Dashboard inicial (grado fondo)

Dos apartados claramente separados, look de tiles ricos (referencias visuales aportadas: KPI tiles arriba, donuts, barras, series temporales, mapa de activos por ubicación, sensación real-time):

- **CARTERA** (solo `operational`): KPIs agregados **reales** (NAV/valor de cartera, ingresos YTD real vs plan, % cumplimiento, desviación agregada, nº activos) + tabla por activo (BASE vs LIVE, desviación, último dato) + visualizaciones (donut por tipo/sector, barras por activo, serie de progreso agregada, **mapa por ubicación** opcional) + drill-in al detalle.
- **OPORTUNIDADES** (solo `opportunity`): simulaciones/valoraciones; NO suman a cartera. Tabla + KPIs de valoración (VAN/TIR/MOIC) + botón **"Marcar en operación / Adquirido"** que promueve a cartera (fija `commissioning_date`, congela BASE).

### Detalle de activo (drill-in)
- **Operativo:** cabecera BASE vs LIVE (VAN/TIR/desviación) · gráfico real vs base+reproyección a lo largo del tiempo · tabla de varianza por línea/periodo (real / modelo / desv. / acumulado / % cumplimiento) · **rejilla de entrada de datos** (meter el dato del día/mes por línea) · editor de inputs (actualizar supuestos futuros: O&M, precios, deuda) · curvas editables (ya existe) · cuenta de resultados + FCF.
- **Oportunidad:** el editor de inputs + KPIs + curvas + cuenta de resultados/FCF actuales (lo de v2), más el botón de promover.

## 5. API (nueva / extendida)

- `PATCH /api/assets/{id}/lifecycle` — promover a operación (fija `commissioning_date`, `tracking_frequency`, congela BASE) o degradar.
- `GET /api/assets?lifecycle=operational|opportunity` — listado filtrado por ciclo de vida.
- `GET /api/assets/{id}/lines` — líneas del modelo del activo trackeables (derivado de `schema_tree` + las líneas de salida de `FinancialOutput`), para elegir qué se registra.
- `POST /api/assets/{id}/actuals` — alta/edición de reales (`period_start`, `line_path`, `value`, `unit`, `note`). Acepta lote.
- `GET /api/assets/{id}/actuals` — serie de reales (filtrable por línea/rango).
- `DELETE /api/assets/{id}/actuals/{actual_id}`.
- `GET /api/assets/{id}/live` — `FinancialOutput` LIVE + comparación con BASE + varianza por línea/periodo.
- `GET /api/portfolio` (extender) — separar agregados de `operational` (cartera real, con KPIs live) vs `opportunity`.
- Token auth en todo (igual que el resto).

## 6. Fases de construcción

- **F1 — Ciclo de vida + dashboard split.** Migración aditiva (`lifecycle`, `commissioning_date`, `base_locked`, `tracking_frequency`). `PATCH /lifecycle`, listado filtrado, `/portfolio` separado. Frontend: dashboard con dos apartados (Cartera / Oportunidades), tiles KPI, transición "Marcar en operación". *(Sin tocar el motor.)*
- **F2 — Captura de reales + varianza.** Tabla `asset_actuals` + store + endpoints actuals + `/lines`. Frontend: rejilla de entrada de datos por activo/periodo/línea + vista **real vs base** (desviación, acumulado, % cumplimiento) con gráficos. *(Aún sin reproyectar la valoración.)*
- **F3 — Escenario LIVE (motor).** Overlay por agregación: `compute_live(scenario, actuals)` → `FinancialOutput` LIVE. Endpoint `/live`. Frontend: cabecera y tarjetas **BASE vs LIVE** + gráfico real+reproyección.
- **F4 — Riqueza fondo.** Alertas por desviación, mapa de activos por ubicación, KPIs ricos, export, dark theme "operations", refinamiento visual a nivel de las referencias.

Cada fase produce software funcional y testeable por sí sola.

## 7. Testing

- Migración aditiva: filas existentes siguen cargando; defaults correctos.
- Ciclo de vida: promover fija fecha + congela base; listado filtra por `lifecycle`; portfolio separa operativos de oportunidades.
- `asset_actuals`: CRUD; agregación por periodo/línea; multi-tenant aislado.
- LIVE: con actuals que igualan el modelo, LIVE ≈ BASE (varianza ~0); con actuals por encima/por debajo, VAN/TIR live se mueven en la dirección correcta; periodos pasados usan reales, futuros usan supuestos.
- API: cada endpoint con token; sin token → 401.
- No rompe los tests existentes (motor + web) ni la v1/v2 (`/api/hybrid_consolidated/*`, `/api/models`, curvas, cartera v2).

## 8. Criterios de aceptación

1. El dashboard inicial separa **Cartera (operación)** de **Oportunidades**; una oportunidad se promueve a operación congelando su BASE.
2. En un activo operativo se meten datos reales contra **cualquier línea de su propio modelo**, a la frecuencia configurada, y se ve la **desviación frente al BASE** (varianza, acumulado, % cumplimiento).
3. El **LIVE** recalcula VAN/TIR con reales-hasta-hoy + reproyección, mostrado **al lado del BASE**.
4. Funciona para **cualquier tipo de activo** (renovable, industrial, empresa, inmobiliario…) sin hardcode — driven por el schema del activo.
5. UI **grado fondo, sin emojis**, rica y visual (tiles, charts, drill-in).
6. Token auth; multi-tenant por `user_id`/`workspace_id`. No rompe nada de v1/v2.
7. Arquitectura lista para **migrar al webOS** del agente (mismo contrato JSON; el agente llama estos endpoints por voz/chat).

## 9. Fuera de alcance (posterior)

- Motor multi-periodo nativo (mensual real) — el overlay por agregación cubre el LIVE; v4 si hiciera falta.
- Ingesta automática de datos reales (APIs SCADA/contabilidad) — de momento entrada manual + lote; conectores después.
- Permisos finos por rol dentro de un workspace (más allá del aislamiento por tenant ya existente).
