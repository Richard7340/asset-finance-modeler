import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ComposableMap, Geographies, Geography, Marker } from "react-simple-maps";
import { MapPin } from "lucide-react";
import { listAssets } from "../api";
import type { Lifecycle, SavedAssetSummary } from "../api";
import { eur } from "../format";
import { useChartTheme } from "../hooks/useChartTheme";

// World topojson served statically (no API key, same-origin). Copied from
// world-atlas (countries-110m) into /public so it never hits the network of a
// third party and stays out of the JS bundle.
const GEO_URL = `${import.meta.env.BASE_URL}world-110m.json`;

/** A plottable asset: a saved asset that carries coordinates. */
type Plotted = {
  id: string;
  name: string;
  npv: number;
  lifecycle: Lifecycle;
  lat: number;
  lon: number;
};

function npvOf(a: SavedAssetSummary): number {
  const k = a.kpis ?? {};
  return Number(k.npv ?? k.npv_hybrid ?? 0) || 0;
}

function hasCoords(a: SavedAssetSummary): boolean {
  return (
    typeof a.lat === "number" &&
    Number.isFinite(a.lat) &&
    typeof a.lon === "number" &&
    Number.isFinite(a.lon)
  );
}

// Lifecycle marker tones (sober, theme-shared with the rest of the app).
const TONE: Record<Lifecycle, string> = {
  operational: "#4f46e5", // indigo-600
  opportunity: "#64748b", // slate-500
};

type Props = {
  /** Drill into an asset when its marker is clicked. */
  onOpenAsset?: (a: SavedAssetSummary) => void;
};

/**
 * Portfolio map (F4-2): plots saved assets that carry coordinates on a sober
 * world map centered on the Iberian region (where the renewables portfolio
 * lives). Assets without coordinates are not plotted; the count is surfaced.
 * No API key — the geography is a static topojson served from /public.
 */
export default function AssetsMap({ onOpenAsset }: Props) {
  const ct = useChartTheme();
  const { data, isLoading } = useQuery({
    queryKey: ["assets", "map"],
    queryFn: () => listAssets(),
  });
  const assets = data ?? [];

  const [hover, setHover] = useState<{ p: Plotted; x: number; y: number } | null>(
    null,
  );

  const plotted: Plotted[] = useMemo(
    () =>
      assets.filter(hasCoords).map((a) => ({
        id: a.id,
        name: a.name,
        npv: npvOf(a),
        lifecycle: a.lifecycle,
        lat: a.lat as number,
        lon: a.lon as number,
      })),
    [assets],
  );

  const unplotted = assets.length - plotted.length;

  // Geography tones for the two themes.
  const geoFill = ct.dark ? "#1c2740" : "#eef2f7";
  const geoStroke = ct.dark ? "#0b1220" : "#ffffff";

  if (isLoading) {
    return (
      <div className="grid h-64 place-items-center text-sm text-slate-400">
        Cargando mapa…
      </div>
    );
  }

  return (
    <section className="surface p-4">
      <div className="mb-1 flex items-baseline justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
          <MapPin size={15} strokeWidth={2} className="text-accent-600" />
          Mapa de activos
        </h3>
        <span className="text-[11px] text-slate-400">
          {plotted.length} con ubicación
          {unplotted > 0 ? ` · ${unplotted} sin coordenadas` : ""}
        </span>
      </div>
      <p className="mb-3 text-xs text-slate-500">
        Activos de la cartera con coordenadas. Los activos sin ubicación no se
        muestran en el mapa.
      </p>

      {plotted.length === 0 ? (
        <div className="grid h-64 place-items-center px-6 text-center text-xs text-slate-400">
          Ningún activo guardado tiene coordenadas todavía. Añade latitud y
          longitud al guardar un activo para verlo aquí.
        </div>
      ) : (
        <div className="relative">
          <ComposableMap
            projection="geoMercator"
            projectionConfig={{ center: [3, 42], scale: 700 }}
            width={760}
            height={420}
            style={{ width: "100%", height: "auto" }}
          >
            <Geographies geography={GEO_URL}>
              {({ geographies }) =>
                geographies.map((geo) => (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill={geoFill}
                    stroke={geoStroke}
                    strokeWidth={0.5}
                    style={{
                      default: { outline: "none" },
                      hover: { outline: "none", fill: geoFill },
                      pressed: { outline: "none" },
                    }}
                  />
                ))
              }
            </Geographies>
            {plotted.map((p) => (
              <Marker
                key={p.id}
                coordinates={[p.lon, p.lat]}
                onMouseEnter={(e: React.MouseEvent) =>
                  setHover({ p, x: e.clientX, y: e.clientY })
                }
                onMouseMove={(e: React.MouseEvent) =>
                  setHover({ p, x: e.clientX, y: e.clientY })
                }
                onMouseLeave={() => setHover(null)}
                onClick={() => {
                  const a = assets.find((x) => x.id === p.id);
                  if (a && onOpenAsset) onOpenAsset(a);
                }}
                style={{ default: { cursor: onOpenAsset ? "pointer" : "default" } }}
              >
                <circle
                  r={5}
                  fill={TONE[p.lifecycle]}
                  fillOpacity={0.85}
                  stroke={ct.dark ? "#0b1220" : "#ffffff"}
                  strokeWidth={1.5}
                />
              </Marker>
            ))}
          </ComposableMap>

          {/* Legend */}
          <div className="mt-2 flex flex-wrap items-center gap-4 text-[11px] text-slate-500">
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: TONE.operational }}
              />
              En operación
            </span>
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: TONE.opportunity }}
              />
              Oportunidad
            </span>
          </div>

          {hover && (
            <div
              className="pointer-events-none fixed z-50 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs shadow-lg dark:border-slate-700 dark:bg-ink-800"
              style={{ left: hover.x + 12, top: hover.y + 12 }}
            >
              <div className="font-semibold text-slate-800">{hover.p.name}</div>
              <div className="mt-0.5 text-slate-500">
                VAN{" "}
                <span className="tabular-nums text-slate-700">
                  {eur(hover.p.npv)}
                </span>
              </div>
              <div className="text-slate-400">
                {hover.p.lifecycle === "operational"
                  ? "En operación"
                  : "Oportunidad"}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
