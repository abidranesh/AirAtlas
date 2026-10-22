import type { RegionCode } from "./types";

/** Coverage caveats shown on each region page. Facts from docs/phase-1-data-sources.md and phase-3-ingestion.md. */
export const REGION_NOTES: Record<RegionCode, string[]> = {
  tamil_nadu: [
    "Hourly concentrations come from CPCB/TNPCB monitors via OpenAQ. When that feed lags, monitors show CPCB's official index exactly as published on data.gov.in, and district colours fall back to modeled estimates.",
  ],
  kerala: [
    "Hourly concentrations come from Kerala PCB monitors via OpenAQ. When that feed lags, monitors show CPCB's official index exactly as published on data.gov.in, and district colours fall back to modeled estimates.",
    "Kochi has no city-centre monitor; the nearest is the Eloor industrial belt in Ernakulam district.",
  ],
  uae: [
    "No UAE authority publishes open hourly data. Measured values come from low-cost sensors (AirGradient, via OpenAQ), almost all in Dubai. Abu Dhabi, Sharjah, Fujairah and Umm al-Quwain rely on modeled data.",
    "Modeled data includes desert dust, which drives many of the UAE's PM10 peaks.",
  ],
  germany: [
    "Around 420 official monitors from the Umweltbundesamt (UBA). UBA publishes each hour about 3–4 hours late.",
  ],
};

export const FEATURED_LABEL: Record<RegionCode, string> = {
  tamil_nadu: "Chennai",
  kerala: "Kochi (Ernakulam)",
  uae: "Dubai",
  germany: "Berlin",
};
