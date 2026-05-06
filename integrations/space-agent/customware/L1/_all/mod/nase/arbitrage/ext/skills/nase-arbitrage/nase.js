import {
  DEFAULT_SCOUT_POLICY,
  createTradeIntentDraft,
  evaluateOpportunity,
  normalizePolicy,
  rankScoutSignals,
  resolveExecutableLegs,
  simulatePaperTrade,
} from "../../../policy.js";

const DEFAULT_NASE_API_BASE = "http://127.0.0.1:8787";
const DEFAULT_NASE_EXECUTOR_BASE = "http://127.0.0.1:8790";
const dashboardUrl = "https://phd-postcard-brief-representation.trycloudflare.com/";

function apiBase() {
  return globalThis.NASE_API_BASE || globalThis.localStorage?.getItem?.("nase:apiBase") || DEFAULT_NASE_API_BASE;
}

function executorBase() {
  return globalThis.NASE_EXECUTOR_BASE || globalThis.localStorage?.getItem?.("nase:executorBase") || DEFAULT_NASE_EXECUTOR_BASE;
}

function proxyUrl(path, base = apiBase()) {
  const target = new URL(path, base);
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

async function getExecutorJson(path) {
  const response = await fetch(proxyUrl(path, executorBase()), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`NASE executor ${path} failed: HTTP ${response.status}`);
  }
  return await response.json();
}

async function postExecutorJson(path, payload) {
  const response = await fetch(proxyUrl(path, executorBase()), {
    method: "POST",
    cache: "no-store",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok && response.status !== 422) {
    throw new Error(`NASE executor ${path} failed: HTTP ${response.status}`);
  }
  return data;
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

export async function scoutOnce(policy = {}) {
  const safePolicy = normalizePolicy(policy);
  const params = {
    limit: safePolicy.maxExplain,
    min_confidence: Math.max(0, safePolicy.minConfidence - 15),
    min_spread: Math.max(0, safePolicy.minSpreadPct * 0.5),
  };
  const [opportunityData, alertData, sourceData] = await Promise.all([
    opportunities(params),
    alerts(),
    sources(),
  ]);
  const alertItems = alertData.alerts || [];
  const sourceItems = sourceData.sources || [];
  const explanations = [];
  for (const opportunity of (opportunityData.opportunities || []).slice(0, safePolicy.maxExplain)) {
    try {
      explanations.push(await explain(opportunity.id));
    } catch (error) {
      explanations.push({
        opportunity,
        analysis: {
          caveats: [error?.message || String(error)],
          executable_related_quotes: 0,
          actionability: "blocked",
        },
        related_quotes: [],
      });
    }
  }
  const signals = rankScoutSignals(
    explanations.map((payload) => evaluateOpportunity(payload, { alerts: alertItems, sources: sourceItems }, safePolicy)),
  );
  return {
    mode: "scout",
    cycle: opportunityData.cycle || alertData.cycle || 0,
    updated_at: opportunityData.updated_at || alertData.updated_at || null,
    policy: safePolicy,
    alerts: alertItems,
    sources: sourceItems,
    count: signals.length,
    actionable_count: signals.filter((signal) => signal.status === "actionable").length,
    review_count: signals.filter((signal) => signal.status === "review").length,
    blocked_count: signals.filter((signal) => signal.status === "blocked").length,
    signals,
  };
}

export async function paperTradeTop(policy = {}) {
  const scout = await scoutOnce(policy);
  const entries = [];
  for (const signal of scout.signals.filter((item) => item.status !== "blocked").slice(0, 5)) {
    const payload = await explain(signal.id);
    entries.push(simulatePaperTrade(payload, { alerts: scout.alerts, sources: scout.sources, evaluation: signal }, scout.policy));
  }
  return {
    mode: "paper",
    cycle: scout.cycle,
    updated_at: scout.updated_at,
    policy: scout.policy,
    entries,
    scout,
  };
}

export async function tradeIntentFor(idOrIndex, policy = {}) {
  const safePolicy = normalizePolicy(policy);
  const [payload, alertData, sourceData] = await Promise.all([
    explain(idOrIndex),
    alerts(),
    sources(),
  ]);
  const context = { alerts: alertData.alerts || [], sources: sourceData.sources || [] };
  const evaluation = evaluateOpportunity(payload, context, safePolicy);
  const paper = simulatePaperTrade(payload, { ...context, evaluation }, safePolicy);
  return createTradeIntentDraft(payload, { ...context, evaluation, paper }, safePolicy);
}

export async function executorHealth() {
  return await getExecutorJson("/health");
}

export async function executorLedger(limit = 25) {
  return await getExecutorJson(`/api/ledger?limit=${encodeURIComponent(String(limit))}`);
}

export async function startPaperRun(options = {}) {
  return await postExecutorJson("/api/paper-runs", options);
}

export async function paperRuns() {
  return await getExecutorJson("/api/paper-runs");
}

export async function paperRun(id) {
  return await getExecutorJson(`/api/paper-runs/${encodeURIComponent(String(id))}`);
}

export async function validateIntentWithExecutor(intent, options = {}) {
  return await postExecutorJson("/api/intents/validate", { intent, human_confirmed: Boolean(options.human_confirmed) });
}

export async function submitIntentToExecutor(intent, options = {}) {
  return await postExecutorJson("/api/intents/submit", { intent, human_confirmed: Boolean(options.human_confirmed) });
}

export {
  DEFAULT_SCOUT_POLICY,
  createTradeIntentDraft,
  dashboardUrl,
  evaluateOpportunity,
  executorBase,
  normalizePolicy,
  rankScoutSignals,
  resolveExecutableLegs,
  simulatePaperTrade,
};
