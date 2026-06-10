# Diseño — Simulador / Centro de Operaciones Financiero (mini-plataforma web)

**Fecha:** 2026-06-10 · **Autores:** Riky + Aurora · **Repo:** `asset-finance-modeler` · **Estado:** spec para revisión

## 1. Visión

Una plataforma web que actúa como **centro de operaciones financiero de activos**: presenta CUALQUIER activo o portfolio (renovable, industrial, inmobiliario, empresa…) con todos sus inputs, sus datos financieros y sus KPIs, y permite **what-if en vivo** (cambiar inputs y ver moverse los KPIs/flujos/curvas). Es tanto una herramienta de **gestión y control** de activos como una forma de **presentar oportunidades a inversores** con un link, totalmente trazable para una TDD.

El back-end es el motor `asset-finance-modeler` (ya construido y validado). La app se construye **standalone** primero, pero con arquitectura pensada para **migrar luego como app dentro del webOS de Gestnova** (controlable por kernel/agente, voz/chat), de modo que cada usuario vea y simule sus modelos desde su agente.

### Alcance v1 (esta fase)
- **Dashboard interactivo del deal SVJ** (FV+BESS) ya modelado/validado: inputs editables clave + KPIs + flujos + curvas + gráficos, **recálculo en vivo**, descarga **Excel-foto**.
- **Desplegada online con link público** (`sim.gestnova.eu`) protegido por token, para enviar al inversor.
- Arquitectura **general** por debajo (un "deal/model service") aunque la UI v1 se centre en SVJ.

### Fuera de alcance v1 (fases/sesiones posteriores)
- UI multi-modelo / crear-editar cualquier activo desde cero (v2).
- Migración como app dentro del webOS (sesión Torre).
- Multi-tenant, auth de usuarios, wizard end-user.

## 2. Arquitectura

```
[Navegador inversor] --HTTPS--> sim.gestnova.eu (Cloudflare Tunnel)
   --> [Torre Linux · contenedor Docker]
         FastAPI (asset-finance-modeler):
           ├─ /api/*  (endpoints del simulador)
           └─ sirve la SPA React estática (build)
         token de acceso (?t=… o cabecera)
```
Un solo contenedor, un solo link. El frontend estático lo sirve el propio FastAPI (sin CORS ni segundo host).

## 3. Backend (extender `mcp_server/http_server.py` o nuevo `web_api/`)

Endpoints (v1, SVJ; nombrados para generalizar a `/api/model/{id}` en v2):
- `GET /api/svj/model` → definición de inputs editables (clave, label, unidad, default, rango/opciones) + metadatos explicativos. Fuente de verdad de "qué se puede tocar".
- `POST /api/svj/run` → body = overrides de inputs. Construye FV+BESS con overrides, corre `HybridProject` (NPV proy unlevered FV/BESS/híbrido vía `consolidate_npv` con `max_leverage=0`; DSCR senior/sub, MOIC, recovery con la deuda vía `TrancheSpec`). Devuelve JSON: `{kpis:{...}, cashflows:{years, fv, bess, hybrid}, curves:{spread[], ancillary[]}, bridge:{fv, bess, hybrid}, dscr_profile:[]}`.
- `POST /api/svj/export` → genera el Excel-foto (`store/exports.to_xlsx` + hojas del deal) con los overrides actuales y lo devuelve como descarga (`Content-Disposition`).
- Auth: token compartido (env var) validado en cada `/api/*`. Sin token → 401.
- Reusa la lógica de calibración del deal (presets `svj_fv_cordoba`/`svj_bess_cordoba` + `HybridProject`) en un módulo `deals/svj.py` que el endpoint llama (1 sola fuente de verdad de cómo se arma el deal).

## 4. Frontend (`web/` — React 19 + Vite + Tailwind v4 + recharts)

Mismo stack que `gestnova-web` (→ migrable al webOS). SPA de una página:
- **Panel de inputs** (lateral): drivers clave editables con label+unidad+ayuda — escenario/curva de spread, curva ancillary, capex €/kWh, plazo deuda inversor, tipos senior/sub, opex, % carga FV, WACC/Ke. Sliders + campos numéricos.
- **KPIs** (tarjetas arriba): NPV FV/BESS/híbrido, DSCR sub (avg/min), MOIC, recovery, IRR — con color/estado (verde/ámbar).
- **Gráficos** (recharts): flujos de caja anuales (barras FV/BESS/híbrido), curvas de revenue (spread + ancillary, 30a), bridge FV→BESS→híbrido, perfil DSCR año a año.
- **Recálculo en vivo:** al cambiar un input → react-query + debounce (~300ms) → `POST /api/svj/run` → actualiza KPIs+gráficos. Indicador de "recalculando".
- **Descargar Excel** (botón → `/api/svj/export`).
- **Escenarios:** guardar/comparar localmente (localStorage v1; el store de provenance del motor queda para v2/webOS).
- **Trazabilidad TDD:** sección "supuestos & fuentes" mostrando cada input, su valor y su fuente (curvas Agere/Modo, etc.).
- **webOS-ready:** base de API por env/config (`VITE_API_BASE`), y un flag `?embed=1` que oculta el cromo (header/nav) para incrustar como iframe en el webOS.

## 5. Deploy

- `Dockerfile` multi-stage: (1) build de la SPA (node) → (2) imagen Python con FastAPI + el build estático + el motor. Un puerto.
- En la torre: `docker run` (o compose) + **Cloudflare Tunnel** a `sim.gestnova.eu`. Token en el env.
- Documentar el `docker build/run` + la config del túnel en `web/README.md`.

## 6. Testing
- **Backend:** pytest sobre `/api/svj/model`, `/api/svj/run` (asierta KPIs reproducen los validados: NPV híbrido ~€1.032k, MOIC 1,37×, DSCR sub avg ~1,20), `/api/svj/export` (devuelve un xlsx no vacío), auth (401 sin token).
- **Frontend:** test de componentes clave (panel inputs, tarjetas KPI) + el flujo recalc (mock de `/api/svj/run`).
- **E2E ligero:** levantar el contenedor, pedir `/api/svj/run`, validar el JSON.

## 7. Criterios de aceptación (v1)
1. `docker run` levanta FastAPI sirviendo la SPA + `/api/*` en un puerto, con token.
2. La SPA muestra el deal SVJ con KPIs/flujos/curvas/bridge correctos (coinciden con el modelo validado).
3. Cambiar un input recalcula los KPIs/gráficos en vivo (<1s percibido).
4. Descarga del Excel-foto funciona.
5. Accesible vía `sim.gestnova.eu` (Cloudflare Tunnel) con token; sin token → 401.
6. Arquitectura limpia y documentada para migrar al webOS (API base configurable, embed mode, contrato JSON estable).

## 8. Notas de migración webOS (no construir aquí)
La SPA autocontenida + el contrato JSON estable permiten incrustarla como app webOS (iframe-kernel-bridge) en una sesión posterior; el agente/kernel llamará la misma API (`/api/.../run`) por voz/chat. Generalizar `/api/svj/*` → `/api/model/{id}/*` será el paso v2 para cualquier activo/portfolio.
