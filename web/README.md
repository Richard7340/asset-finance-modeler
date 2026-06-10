# Simulador Financiero Gestnova — frontend + deploy

SPA React (Vite + Tailwind v4 + react-query + recharts) que consume la API del motor
(`/api/svj/*`). En producción, el propio FastAPI del motor sirve esta SPA construida
(`web/dist`) + la API en un solo puerto.

## Desarrollo local

```bash
# 1) Backend (sirve /api y, si existe web/dist, también la SPA) en :8015
cd <repo>
PYTHONPATH=src .venv/bin/python -m asset_finance_modeler.mcp_server.http_server   # PORT=8015

# 2) Frontend en modo dev (proxy /api -> :8015), hot-reload en :5173
cd web && npm install && npm run dev
# abrir http://localhost:5173
```

Para ver la SPA servida por el backend (como en producción):
```bash
cd web && npm run build         # genera web/dist
# reinicia el backend -> abre http://localhost:8015
```

## Despliegue (torre + Cloudflare Tunnel)

```bash
# Construir la imagen (incluye build del frontend)
docker build -t gestnova-sim .

# Correr en la torre (token protege el enlace; volumen para escenarios)
docker run -d --name gestnova-sim \
  -e SIM_TOKEN="<token-secreto>" \
  -e PORT=8015 \
  -p 8015:8015 \
  -v /datos/gestnova-sim/scenarios:/data/scenarios \
  gestnova-sim

# Exponer vía Cloudflare Tunnel a sim.gestnova.eu
#   cloudflared tunnel route dns <tunnel> sim.gestnova.eu
#   ingress:  hostname sim.gestnova.eu  ->  service http://localhost:8015
cloudflared tunnel run <tunnel>
```

**Link al inversor:** `https://sim.gestnova.eu/?t=<token-secreto>`
(sin `?t=` correcto → 401 en `/api/*`). El token se valida por query `?t=` o cabecera `x-sim-token`.

## Notas
- `SIM_TOKEN` sin definir = API abierta (solo para dev local).
- La imagen pone `SIM_WEB_DIST=/app/web/dist`; el backend lo prioriza para localizar la SPA.
- Migración webOS (futuro): la SPA es autocontenida (`VITE_API_BASE` configurable + `?embed=1`
  oculta el header) → embebible como app del webOS vía iframe-kernel-bridge, llamando la misma API.
