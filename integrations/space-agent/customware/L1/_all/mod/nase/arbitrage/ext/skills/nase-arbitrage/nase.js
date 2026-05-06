const NASE_API_BASE = "http://127.0.0.1:8787";
const dashboardUrl = "https://phd-postcard-brief-representation.trycloudflare.com/";

function proxyUrl(path) {
  const target = new URL(path, NASE_API_BASE);
  return `/api/proxy?url=${encodeURIComponent(target.toString())}`;
}

async function getJson(path) {
  const response = await fetch(proxyUrl(path), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`NASE ${path} failed: HTTP ${response.status}`);
  }
  return await response.json();
}

async function postJson(path) {
  const response = await fetch(proxyUrl(path), { method: "POST", cache: "no-store" });
  if (!response.ok) {
    throw new Error(`NASE ${path} failed: HTTP ${response.status}`);
  }
  return await response.json();
}

export async function snapshot() {
  return await getJson("/api/snapshot");
}

export async function sources() {
  return await getJson("/api/sources");
}

export async function sourceHealth() {
  return (await sources()).sources || [];
}

export async function opportunities(options = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(options)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const suffix = params.toString() ? `?${params}` : "";
  return await getJson(`/api/opportunities${suffix}`);
}

export async function topOpportunities(limit = 10) {
  return (await opportunities({ limit })).opportunities || [];
}

export async function alerts() {
  return await getJson("/api/alerts");
}

export async function explain(idOrIndex) {
  return await getJson(`/api/explain/${encodeURIComponent(String(idOrIndex))}`);
}

export async function refresh() {
  return await postJson("/api/refresh");
}

export async function executableQuotes() {
  const data = await snapshot();
  return (data.top_quotes || []).filter((quote) => quote.executable);
}

export async function executableWethUsdcSanity() {
  const quotes = (await executableQuotes()).filter((quote) => quote.pair === "WETH/USDC" || quote.pair === "WETH.e/USDC");
  const groups = new Map();
  for (const quote of quotes) {
    const key = `${quote.pair}:${quote.chain}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(quote);
  }
  return [...groups.entries()].map(([key, items]) => {
    const prices = items.map((item) => Number(item.price)).filter((value) => Number.isFinite(value) && value > 0);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    return {
      key,
      sources: items.map((item) => item.source),
      count: items.length,
      min,
      max,
      spread_pct: min > 0 ? ((max - min) / min) * 100 : 0,
    };
  });
}

export { dashboardUrl };
