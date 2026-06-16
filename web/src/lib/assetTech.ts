import {
  Sun,
  BatteryCharging,
  Wind,
  Server,
  Layers,
  Home,
  Briefcase,
  Building2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

/** A sober tech descriptor for an asset, derived from its model id. */
export type AssetTech = {
  /** Short Spanish label for the tech/type chip. */
  label: string;
  /** Lucide icon component (no emojis). */
  Icon: LucideIcon;
};

/**
 * Map a model id (e.g. "solar", "bess", "svj_hybrid", "real_estate") to a
 * human label + lucide icon. Matches on substrings so model-id variants
 * ("svj_hybrid", "solar_pv", …) still resolve. Falls back to a neutral tag.
 */
export function assetTech(modelId: string | undefined): AssetTech {
  const id = (modelId ?? "").toLowerCase();
  if (id.includes("solar") || id.includes("pv") || id.includes("fv"))
    return { label: "Solar FV", Icon: Sun };
  if (id.includes("bess") || id.includes("storage") || id.includes("batt"))
    return { label: "Almacenamiento", Icon: BatteryCharging };
  if (id.includes("wind") || id.includes("eolic") || id.includes("eolico"))
    return { label: "Eólica", Icon: Wind };
  if (id.includes("data") || id.includes("dc"))
    return { label: "Data center", Icon: Server };
  if (id.includes("svj") || id.includes("hybrid") || id.includes("hibrido"))
    return { label: "Híbrido", Icon: Layers };
  if (id.includes("real_estate") || id.includes("inmob") || id.includes("estate"))
    return { label: "Inmobiliario", Icon: Home };
  if (id.includes("business") || id.includes("negocio"))
    return { label: "Negocio", Icon: Briefcase };
  return { label: modelId ?? "Activo", Icon: Building2 };
}
