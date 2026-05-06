export const LIVE_EXECUTION_STYLES = Object.freeze(["limit_only", "hybrid", "market_exact_in"]);
export const PAPER_EXECUTION_STYLES = Object.freeze(["market_exact_in", "limit_hypothesis"]);
export const EXECUTION_STYLES = LIVE_EXECUTION_STYLES;

export const DEFAULT_SCOUT_POLICY = Object.freeze({
  minConfidence: 85,
  minSpreadPct: 0.25,
  minNetEdgeUsd: 1,
  maxAgeSeconds: 120,
  requireExecutableRelated: true,
  requireExecutableLegs: true,
  blockCriticalSources: true,
  maxExplain: 12,
  paperBudgetUsd: 500,
  maxBudgetPerTradeUsd: 250,
  maxDailyBudgetUsd: 1000,
  slippageBps: 12,
  dexFeeBps: 6,
  latencyHaircutBps: 4,
  confidenceHaircutPct: 0.25,
  paperExecutionStyle: "market_exact_in",
  liveExecutionStyle: "limit_only",
  quoteTtlSeconds: 10,
  maxLiveSlippageBps: 8,
  limitBufferBps: 2,
  humanConfirmUsd: 1000,
  requireFreshExecutorQuote: true,
  requireExecutorSimulation: true,
  defaultGasUsd: 1,
  chainGasUsd: {
    ethereum: 8,
    arbitrum: 0.5,
    base: 0.3,
    optimism: 0.3,
    polygon: 0.1,
    bsc: 0.25,
    avalanche: 0.4,
    solana: 0.01,
    zksync: 0.2,
    linea: 0.25,
  },
  chainAllowlist: [],
  tokenAllowlist: [],
  tokenDenylist: [],
  dexAllowlist: [],
});

export function normalizePolicy(policy = {}) {
  const merged = { ...DEFAULT_SCOUT_POLICY, ...policy };
  if (policy.executionStyle && !policy.liveExecutionStyle) merged.liveExecutionStyle = policy.executionStyle;
  merged.chainGasUsd = { ...DEFAULT_SCOUT_POLICY.chainGasUsd, ...(policy.chainGasUsd || {}) };
  for (const key of ["chainAllowlist", "tokenAllowlist", "tokenDenylist", "dexAllowlist"]) {
    merged[key] = normalizeList(merged[key]);
  }
  for (const key of [
    "minConfidence",
    "minSpreadPct",
    "minNetEdgeUsd",
    "maxAgeSeconds",
    "maxExplain",
    "paperBudgetUsd",
    "maxBudgetPerTradeUsd",
    "maxDailyBudgetUsd",
    "slippageBps",
    "dexFeeBps",
    "latencyHaircutBps",
    "confidenceHaircutPct",
    "quoteTtlSeconds",
    "maxLiveSlippageBps",
    "limitBufferBps",
    "humanConfirmUsd",
    "defaultGasUsd",
  ]) {
    merged[key] = finiteNumber(merged[key], DEFAULT_SCOUT_POLICY[key]);
  }
  merged.maxExplain = Math.max(1, Math.min(50, Math.round(merged.maxExplain)));
  merged.paperBudgetUsd = Math.max(0, merged.paperBudgetUsd);
  merged.maxBudgetPerTradeUsd = Math.max(0, merged.maxBudgetPerTradeUsd);
  merged.maxDailyBudgetUsd = Math.max(0, merged.maxDailyBudgetUsd);
  merged.quoteTtlSeconds = Math.max(1, Math.round(merged.quoteTtlSeconds));
  merged.maxLiveSlippageBps = Math.max(0, merged.maxLiveSlippageBps);
  merged.limitBufferBps = Math.max(0, merged.limitBufferBps);
  merged.humanConfirmUsd = Math.max(0, merged.humanConfirmUsd);
  merged.paperExecutionStyle = PAPER_EXECUTION_STYLES.includes(merged.paperExecutionStyle)
    ? merged.paperExecutionStyle
    : DEFAULT_SCOUT_POLICY.paperExecutionStyle;
  merged.liveExecutionStyle = LIVE_EXECUTION_STYLES.includes(merged.liveExecutionStyle)
    ? merged.liveExecutionStyle
    : DEFAULT_SCOUT_POLICY.liveExecutionStyle;
  merged.executionStyle = merged.liveExecutionStyle;
  merged.requireExecutableRelated = Boolean(merged.requireExecutableRelated);
  merged.requireExecutableLegs = Boolean(merged.requireExecutableLegs);
  merged.blockCriticalSources = Boolean(merged.blockCriticalSources);
  merged.requireFreshExecutorQuote = Boolean(merged.requireFreshExecutorQuote);
  merged.requireExecutorSimulation = Boolean(merged.requireExecutorSimulation);
  return merged;
}

export function evaluateOpportunity(explainPayload, context = {}, policy = {}) {
  const safePolicy = normalizePolicy(policy);
  const opportunity = explainPayload?.opportunity || explainPayload || {};
  const analysis = explainPayload?.analysis || {};
  const relatedQuotes = explainPayload?.related_quotes || [];
  const pair = String(opportunity.pair || "");
  const base = String(opportunity.base || pair.split("/")[0] || "").toLowerCase();
  const quote = String(opportunity.quote || pair.split("/")[1] || "").toLowerCase();
  const buyDex = String(opportunity.buy_at || "").toLowerCase();
  const sellDex = String(opportunity.sell_at || "").toLowerCase();
  const chains = [opportunity.chain, opportunity.buy_chain, opportunity.sell_chain]
    .filter(Boolean)
    .map((value) => String(value).toLowerCase());
  const sources = (opportunity.sources || []).map((value) => String(value).toLowerCase());
  const confidence = finiteNumber(opportunity.confidence ?? analysis.confidence, 0);
  const spreadPct = finiteNumber(opportunity.spread_pct, 0);
  const ageSeconds = finiteNumber(opportunity.age_seconds, 0);
  const executableRelatedQuotes = finiteNumber(
    analysis.executable_related_quotes,
    relatedQuotes.filter((quoteItem) => quoteItem.executable).length,
  );
  const executableLegs = resolveExecutableLegs(explainPayload);
  const sourceAlerts = (context.alerts || [])
    .filter((alert) => alert?.type === "source_health" && alert?.severity === "critical")
    .map((alert) => String(alert.source || "").toLowerCase());

  const hardBlocks = [];
  const warnings = [];

  if (!opportunity.id) hardBlocks.push("missing opportunity id");
  if (confidence < safePolicy.minConfidence) hardBlocks.push(`confidence ${confidence.toFixed(0)} < ${safePolicy.minConfidence}`);
  if (spreadPct < safePolicy.minSpreadPct) hardBlocks.push(`spread ${spreadPct.toFixed(3)}% < ${safePolicy.minSpreadPct}%`);
  if (safePolicy.maxAgeSeconds > 0 && ageSeconds > safePolicy.maxAgeSeconds) hardBlocks.push(`quote age ${ageSeconds.toFixed(0)}s > ${safePolicy.maxAgeSeconds}s`);
  if (safePolicy.requireExecutableRelated && executableRelatedQuotes < 1) hardBlocks.push("no executable related quote");
  if (safePolicy.requireExecutableLegs && !executableLegs.complete) hardBlocks.push("missing executable buy/sell leg quote");
  if (safePolicy.chainAllowlist.length && !chains.some((chain) => safePolicy.chainAllowlist.includes(chain))) hardBlocks.push("chain outside allowlist");
  if (safePolicy.tokenAllowlist.length && ![base, quote].some((token) => safePolicy.tokenAllowlist.includes(token))) hardBlocks.push("token outside allowlist");
  if (safePolicy.tokenDenylist.some((token) => [base, quote].includes(token))) hardBlocks.push("token denylisted");
  if (safePolicy.dexAllowlist.length && ![buyDex, sellDex].some((dex) => safePolicy.dexAllowlist.includes(dex))) hardBlocks.push("dex outside allowlist");
  if (safePolicy.blockCriticalSources && sources.some((source) => sourceAlerts.includes(source))) hardBlocks.push("critical source health alert");

  if (analysis.actionability && analysis.actionability !== "strong_candidate") warnings.push(`actionability ${analysis.actionability}`);
  for (const caveat of analysis.caveats || []) warnings.push(String(caveat));
  for (const note of opportunity.notes || []) warnings.push(String(note));

  const score = Math.max(
    0,
    Math.min(
      100,
      Math.round(
        confidence
          + Math.min(8, spreadPct * 3)
          + Math.min(8, executableRelatedQuotes * 3)
          + Math.min(6, sources.length * 2)
          - hardBlocks.length * 18
          - Math.min(12, warnings.length * 2),
      ),
    ),
  );
  const status = hardBlocks.length ? "blocked" : warnings.length ? "review" : "actionable";

  return {
    id: opportunity.id || stableId(pair, spreadPct, confidence),
    pair,
    base: opportunity.base || pair.split("/")[0] || "",
    quote: opportunity.quote || pair.split("/")[1] || "",
    chain: opportunity.chain,
    buy_chain: opportunity.buy_chain,
    sell_chain: opportunity.sell_chain,
    buy_at: opportunity.buy_at,
    sell_at: opportunity.sell_at,
    spread_pct: spreadPct,
    confidence,
    age_seconds: ageSeconds,
    executable_related_quotes: executableRelatedQuotes,
    executable_legs: executableLegs,
    sources: opportunity.sources || [],
    status,
    score,
    notify: status === "actionable",
    hard_blocks: hardBlocks,
    warnings: unique(warnings),
    opportunity,
  };
}

export function rankScoutSignals(signals) {
  return [...signals].sort((a, b) => {
    const statusWeight = { actionable: 3, review: 2, blocked: 1 };
    return (
      (statusWeight[b.status] || 0) - (statusWeight[a.status] || 0)
      || b.score - a.score
      || b.spread_pct - a.spread_pct
    );
  });
}

export function simulatePaperTrade(explainPayload, context = {}, policy = {}) {
  const safePolicy = normalizePolicy(policy);
  const evaluation = context.evaluation || evaluateOpportunity(explainPayload, context, safePolicy);
  const executableLegs = evaluation.executable_legs || resolveExecutableLegs(explainPayload);
  const budgetUsd = Math.min(safePolicy.paperBudgetUsd, safePolicy.maxBudgetPerTradeUsd || safePolicy.paperBudgetUsd);
  const executableSpreadPct = finiteNumber(executableLegs.spread_pct, 0);
  const tradableBudgetUsd = executableLegs.max_notional_usd > 0 ? Math.min(budgetUsd, executableLegs.max_notional_usd) : budgetUsd;
  const grossEdgeUsd = tradableBudgetUsd * (executableSpreadPct / 100);
  const dexFeeUsd = tradableBudgetUsd * ((safePolicy.dexFeeBps * 2) / 10000);
  const slippageUsd = tradableBudgetUsd * ((safePolicy.slippageBps * 2) / 10000);
  const gasUsd = gasFor(evaluation.buy_chain || evaluation.chain, safePolicy) + gasFor(evaluation.sell_chain || evaluation.chain, safePolicy);
  const latencyHaircutUsd = grossEdgeUsd * (safePolicy.latencyHaircutBps / 10000);
  const confidenceHaircutUsd = grossEdgeUsd * ((100 - evaluation.confidence) / 100) * safePolicy.confidenceHaircutPct;
  const estimatedNetUsd = grossEdgeUsd - dexFeeUsd - slippageUsd - gasUsd - latencyHaircutUsd - confidenceHaircutUsd;
  const blocked = evaluation.status === "blocked" || !executableLegs.complete || executableSpreadPct <= 0 || estimatedNetUsd < safePolicy.minNetEdgeUsd;
  const paperExecution = buildPaperExecutionAssumption(safePolicy);

  return {
    id: stableId("paper", evaluation.id, Date.now()),
    opportunity_id: evaluation.id,
    pair: evaluation.pair,
    route: `${evaluation.buy_at || "buy"} -> ${evaluation.sell_at || "sell"}`,
    status: blocked ? "paper_reject" : "paper_candidate",
    paper_execution_style: safePolicy.paperExecutionStyle,
    execution_assumption: paperExecution.assumption,
    execution_evidence: executableLegs.evidence_type,
    reference_price_kind: executableLegs.complete ? "executable_quote_depth" : "non_executable_reference",
    uses_last_trade_price: false,
    execution_warning: paperExecution.warning,
    fill_certainty: paperExecution.fill_certainty,
    quote_ttl_seconds: safePolicy.quoteTtlSeconds,
    max_live_slippage_bps: safePolicy.maxLiveSlippageBps,
    budget_usd: round2(tradableBudgetUsd),
    requested_budget_usd: round2(budgetUsd),
    max_notional_usd: round2(executableLegs.max_notional_usd),
    executable_buy_price: numberOrNull(executableLegs.buy_quote?.price),
    executable_sell_price: numberOrNull(executableLegs.sell_quote?.price),
    executable_spread_pct: round6(executableSpreadPct),
    gross_edge_usd: round2(grossEdgeUsd),
    dex_fee_usd: round2(dexFeeUsd),
    slippage_usd: round2(slippageUsd),
    gas_usd: round2(gasUsd),
    latency_haircut_usd: round2(latencyHaircutUsd),
    confidence_haircut_usd: round2(confidenceHaircutUsd),
    estimated_net_usd: round2(estimatedNetUsd),
    confidence: evaluation.confidence,
    spread_pct: executableSpreadPct,
    scanner_spread_pct: evaluation.spread_pct,
    reasons: blocked ? [...evaluation.hard_blocks, executableLegs.complete ? "" : "paper mode requires executable buy and sell legs", executableSpreadPct > 0 ? "" : "non-positive executable spread", `net edge ${round2(estimatedNetUsd)} < ${safePolicy.minNetEdgeUsd}`].filter(Boolean) : [],
    warnings: paperExecution.warning ? [paperExecution.warning] : [],
    created_at: new Date().toISOString(),
    opportunity: evaluation.opportunity,
    executable_legs: executableLegs,
  };
}

export function createTradeIntentDraft(explainPayload, context = {}, policy = {}) {
  const safePolicy = normalizePolicy(policy);
  const evaluation = context.evaluation || evaluateOpportunity(explainPayload, context, safePolicy);
  const paper = context.paper || simulatePaperTrade(explainPayload, { ...context, evaluation }, safePolicy);
  const orderPlan = buildExecutionPlan(evaluation, paper, safePolicy);
  const blockedReasons = [...evaluation.hard_blocks];
  if (paper.estimated_net_usd < safePolicy.minNetEdgeUsd) blockedReasons.push(`paper net edge ${paper.estimated_net_usd} < ${safePolicy.minNetEdgeUsd}`);
  if (safePolicy.maxDailyBudgetUsd <= 0) blockedReasons.push("daily budget is zero");
  if (!orderPlan.executable_legs_complete) blockedReasons.push("execution intent requires executable buy and sell legs");

  return {
    id: stableId("intent", evaluation.id, paper.created_at),
    opportunity_id: evaluation.id,
    pair: evaluation.pair,
    status: blockedReasons.length ? "blocked" : "intent_requires_executor",
    mode: "live_intent_draft",
    requires_executor: true,
    contains_private_key: false,
    signing_allowed_here: false,
    budget_usd: paper.budget_usd,
    max_daily_budget_usd: safePolicy.maxDailyBudgetUsd,
    min_confidence: safePolicy.minConfidence,
    min_net_edge_usd: safePolicy.minNetEdgeUsd,
    paper_execution_style: safePolicy.paperExecutionStyle,
    execution_style: safePolicy.liveExecutionStyle,
    live_execution_style: safePolicy.liveExecutionStyle,
    order_plan: orderPlan,
    quote_ttl_seconds: safePolicy.quoteTtlSeconds,
    max_live_slippage_bps: safePolicy.maxLiveSlippageBps,
    human_confirmation_required: orderPlan.human_confirmation_required,
    executor_requirements: {
      require_fresh_quote: safePolicy.requireFreshExecutorQuote,
      require_transaction_simulation: safePolicy.requireExecutorSimulation,
      quote_ttl_seconds: safePolicy.quoteTtlSeconds,
      max_live_slippage_bps: safePolicy.maxLiveSlippageBps,
      market_order_allowed: orderPlan.market_order_allowed,
      limit_order_required: orderPlan.limit_order_required,
      signer_isolation_required: true,
      kill_switch_required: true,
    },
    guardrails: [
      "executor must enforce token, chain, dex, and budget allowlists",
      "executor must re-quote both legs and reject stale quotes before submission",
      "executor must simulate transactions immediately before signing",
      "executor must reject fills below the order plan price and slippage bounds",
      "executor must own signer isolation and kill switch",
      "Space Agent browser customware must not store private keys",
    ],
    blocked_reasons: blockedReasons,
    paper,
    created_at: new Date().toISOString(),
  };
}

function buildExecutionPlan(evaluation, paper, policy) {
  const executableLegs = evaluation.executable_legs || paper.executable_legs || {};
  const buyQuote = executableLegs.buy_quote || null;
  const sellQuote = executableLegs.sell_quote || null;
  const buyPrice = numberOrNull(buyQuote?.price);
  const sellPrice = numberOrNull(sellQuote?.price);
  const buffer = policy.limitBufferBps / 10000;
  const style = policy.liveExecutionStyle;
  const marketOrderAllowed = style === "market_exact_in" || style === "hybrid";
  const limitOrderRequired = style === "limit_only";
  const fallbackOrderType = style === "hybrid" ? "market_exact_in" : null;
  const buyLimitPrice = buyPrice === null ? null : round6(buyPrice * (1 + buffer));
  const sellLimitPrice = sellPrice === null ? null : round6(sellPrice * (1 - buffer));

  return {
    strategy: style,
    executable_legs_complete: Boolean(executableLegs.complete),
    market_order_allowed: marketOrderAllowed,
    limit_order_required: limitOrderRequired,
    fallback_market_allowed: style === "hybrid",
    quote_ttl_seconds: policy.quoteTtlSeconds,
    max_slippage_bps: policy.maxLiveSlippageBps,
    limit_buffer_bps: policy.limitBufferBps,
    reference_spread_pct: round6(executableLegs.spread_pct),
    scanner_spread_pct: round6(evaluation.spread_pct),
    max_notional_usd: round2(executableLegs.max_notional_usd),
    budget_usd: round2(paper.budget_usd),
    min_expected_net_usd: policy.minNetEdgeUsd,
    expected_net_usd: round2(paper.estimated_net_usd),
    human_confirmation_usd: policy.humanConfirmUsd,
    human_confirmation_required: policy.humanConfirmUsd > 0 && paper.budget_usd >= policy.humanConfirmUsd,
    legs: [
      {
        side: "buy",
        venue: evaluation.buy_at,
        chain: evaluation.buy_chain || evaluation.chain,
        reference_quote_id: buyQuote?.id || null,
        reference_price: buyPrice,
        reference_notional_usd: numberOrNull(buyQuote?.notional_usd),
        order_type: style === "market_exact_in" ? "market_exact_in" : "limit",
        fallback_order_type: fallbackOrderType,
        max_price: buyLimitPrice,
        max_slippage_bps: policy.maxLiveSlippageBps,
      },
      {
        side: "sell",
        venue: evaluation.sell_at,
        chain: evaluation.sell_chain || evaluation.chain,
        reference_quote_id: sellQuote?.id || null,
        reference_price: sellPrice,
        reference_notional_usd: numberOrNull(sellQuote?.notional_usd),
        order_type: style === "market_exact_in" ? "market_exact_in" : "limit",
        fallback_order_type: fallbackOrderType,
        min_price: sellLimitPrice,
        max_slippage_bps: policy.maxLiveSlippageBps,
      },
    ],
    executor_checks: [
      "fetch fresh executable quotes for both legs",
      "reject if either quote is older than quote_ttl_seconds",
      "reject if fresh net edge is below min_expected_net_usd after gas, fees, and slippage",
      "reject if simulated transaction output violates max_price or min_price",
      "require human confirmation when human_confirmation_required is true",
    ],
  };
}

function buildPaperExecutionAssumption(policy) {
  if (policy.paperExecutionStyle === "limit_hypothesis") {
    return {
      assumption: "limit_fill_hypothesis",
      fill_certainty: "hypothetical",
      warning: "limit paper trade only models the price; it cannot know whether the limit order would have filled",
    };
  }
  return {
    assumption: "market_exact_in_replay",
    fill_certainty: "quote_time_executable",
    warning: "market paper trade used executable quote legs, but real fills can still fail from latency, slippage, MEV, or transaction revert",
  };
}

export function stableId(...parts) {
  let hash = 2166136261;
  const raw = parts.map((part) => String(part ?? "")).join("|");
  for (let index = 0; index < raw.length; index += 1) {
    hash ^= raw.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

function normalizeList(value) {
  if (Array.isArray(value)) return value.map((item) => String(item).trim().toLowerCase()).filter(Boolean);
  if (typeof value === "string") return value.split(",").map((item) => item.trim().toLowerCase()).filter(Boolean);
  return [];
}

function finiteNumber(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function gasFor(chain, policy) {
  const key = String(chain || "").toLowerCase();
  return finiteNumber(policy.chainGasUsd[key], policy.defaultGasUsd);
}

function round2(value) {
  return Math.round(Number(value || 0) * 100) / 100;
}

function unique(items) {
  return [...new Set(items.filter(Boolean))];
}

export function resolveExecutableLegs(explainPayload) {
  const opportunity = explainPayload?.opportunity || explainPayload || {};
  const analysisLegs = explainPayload?.analysis?.executable_legs;
  if (analysisLegs?.complete || analysisLegs?.buy_quote || analysisLegs?.sell_quote) {
    return normalizeLegs(analysisLegs);
  }
  const relatedQuotes = explainPayload?.related_quotes || [];
  const executable = relatedQuotes.filter((quote) => quote?.executable);
  const buyQuote = matchExecutableQuote(executable, opportunity.buy_at, true);
  const sellQuote = matchExecutableQuote(executable, opportunity.sell_at, false);
  return normalizeLegs({
    complete: Boolean(buyQuote && sellQuote && buyQuote.id !== sellQuote.id),
    buy_quote: buyQuote,
    sell_quote: sellQuote,
    source: "related_quotes",
  });
}

function normalizeLegs(legs = {}) {
  const buyQuote = legs.buy_quote || null;
  const sellQuote = legs.sell_quote || null;
  const buyPrice = numberOrNull(buyQuote?.price);
  const sellPrice = numberOrNull(sellQuote?.price);
  const maxNotional = finitePositiveMin(buyQuote?.notional_usd, sellQuote?.notional_usd);
  const declaredMaxNotional = finiteNumber(legs.max_notional_usd, 0);
  const effectiveMaxNotional = declaredMaxNotional > 0 ? declaredMaxNotional : maxNotional;
  const complete = Boolean(
    legs.complete
      && isExecutableQuote(buyQuote)
      && isExecutableQuote(sellQuote)
      && buyPrice
      && sellPrice
      && effectiveMaxNotional > 0,
  );
  const spreadPct = complete ? ((sellPrice - buyPrice) / buyPrice) * 100 : 0;
  return {
    complete,
    buy_quote: buyQuote,
    sell_quote: sellQuote,
    spread_pct: round6(finiteNumber(legs.spread_pct, spreadPct)),
    max_notional_usd: effectiveMaxNotional,
    source: legs.source || "unknown",
    evidence_type: complete ? "executable_quote_depth" : "non_executable_reference",
  };
}

function isExecutableQuote(quote) {
  return Boolean(quote?.executable && finiteNumber(quote?.notional_usd, 0) > 0);
}

function matchExecutableQuote(quotes, target, preferLow) {
  if (!quotes.length) return null;
  const targetNorm = String(target || "").toLowerCase();
  const matched = quotes.filter((quote) => {
    const dex = String(quote.dex || "").toLowerCase();
    return targetNorm && (dex.startsWith(targetNorm) || targetNorm.startsWith(dex));
  });
  const candidates = matched.length ? matched : quotes;
  return [...candidates].sort((a, b) => {
    const delta = finiteNumber(a.price, 0) - finiteNumber(b.price, 0);
    return preferLow ? delta : -delta;
  })[0] || null;
}

function finitePositiveMin(...values) {
  const positives = values.map((value) => finiteNumber(value, 0)).filter((value) => value > 0);
  return positives.length ? Math.min(...positives) : 0;
}

function numberOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function round6(value) {
  return Math.round(Number(value || 0) * 1_000_000) / 1_000_000;
}
