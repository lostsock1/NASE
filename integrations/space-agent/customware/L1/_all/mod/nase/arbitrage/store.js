import {
  DEFAULT_SCOUT_POLICY,
  dashboardUrl,
  normalizePolicy,
  paperTradeTop,
  scoutOnce,
  sources as fetchSources,
  snapshot,
  tradeIntentFor,
} from "./ext/skills/nase-arbitrage/nase.js";
import {
  intentToLedger,
  normalizeLedger,
  paperToLedger,
  recordExecutionResult,
  summarizeLedger,
} from "./ledger.js";

const STORAGE_KEY = "nase:space-agent:automation";

function installStore() {
  const Alpine = globalThis.Alpine;
  if (!Alpine || Alpine.store("naseArbitrage")) return;

  Alpine.store("naseArbitrage", {
    loading: false,
    scouting: false,
    error: "",
    copyStatus: "",
    automationStatus: "idle",
    snapshot: null,
    summary: {},
    sources: [],
    scoutEnabled: false,
    paperEnabled: false,
    intentArmed: false,
    policy: normalizePolicy(DEFAULT_SCOUT_POLICY),
    scoutSignals: [],
    paperJournal: [],
    tradeIntents: [],
    tradeLedger: [],
    seenSignalIds: new Set(),
    timer: null,
    scoutTimer: null,

    async init() {
      this.restoreAutomation();
      await this.refresh();
      this.timer = window.setInterval(() => this.refresh({ quiet: true }), 10000);
      this.scoutTimer = window.setInterval(() => this.runAutomation({ quiet: true }), 15000);
      await this.runAutomation({ quiet: true });
    },

    restoreAutomation() {
      try {
        const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}");
        this.scoutEnabled = Boolean(saved.scoutEnabled);
        this.paperEnabled = Boolean(saved.paperEnabled);
        this.intentArmed = Boolean(saved.intentArmed);
        this.policy = normalizePolicy({ ...DEFAULT_SCOUT_POLICY, ...(saved.policy || {}) });
        this.paperJournal = Array.isArray(saved.paperJournal) ? saved.paperJournal.slice(0, 50) : [];
        this.tradeIntents = Array.isArray(saved.tradeIntents) ? saved.tradeIntents.slice(0, 25) : [];
        this.tradeLedger = normalizeLedger(saved.tradeLedger || []);
      } catch {
        this.policy = normalizePolicy(DEFAULT_SCOUT_POLICY);
      }
    },

    saveAutomation() {
      const payload = {
        scoutEnabled: this.scoutEnabled,
        paperEnabled: this.paperEnabled,
        intentArmed: this.intentArmed,
        policy: this.policy,
        paperJournal: this.paperJournal.slice(0, 50),
        tradeIntents: this.tradeIntents.slice(0, 25),
        tradeLedger: this.tradeLedger.slice(0, 100),
      };
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    },

    async refresh(options = {}) {
      this.loading = !options.quiet;
      this.error = "";
      try {
        this.snapshot = await snapshot();
        this.summary = this.snapshot.summary || {};
        this.sources = (await fetchSources()).sources || this.snapshot.sources || [];
      } catch (error) {
        this.error = error?.message || String(error);
      } finally {
        this.loading = false;
      }
    },

    async runAutomation(options = {}) {
      if (!this.scoutEnabled && !options.force) return;
      if (this.scouting) return;
      this.scouting = true;
      this.automationStatus = options.quiet ? this.automationStatus : "checking";
      try {
        const result = await scoutOnce(this.policy);
        this.policy = result.policy;
        this.scoutSignals = result.signals || [];
        this.automationStatus = `${result.actionable_count} actionable / ${result.review_count} review`;
        this.notifySignals(this.scoutSignals);
        if (this.paperEnabled) {
          const paper = await paperTradeTop(this.policy);
          this.paperJournal = [...paper.entries, ...this.paperJournal].slice(0, 50);
          this.tradeLedger = this.mergeLedger([...paper.entries.map((entry) => paperToLedger(entry)), ...this.tradeLedger]);
        }
        this.saveAutomation();
      } catch (error) {
        this.error = error?.message || String(error);
        this.automationStatus = "error";
      } finally {
        this.scouting = false;
      }
    },

    async draftIntent(signal) {
      if (!this.intentArmed || !signal?.id) return;
      this.scouting = true;
      try {
        const intent = await tradeIntentFor(signal.id, this.policy);
        this.tradeIntents = [intent, ...this.tradeIntents].slice(0, 25);
        this.tradeLedger = this.mergeLedger([intentToLedger(intent), ...this.tradeLedger]);
        this.saveAutomation();
      } catch (error) {
        this.error = error?.message || String(error);
      } finally {
        this.scouting = false;
      }
    },

    toggleScout() {
      this.scoutEnabled = !this.scoutEnabled;
      this.saveAutomation();
      if (this.scoutEnabled) this.runAutomation({ force: true });
    },

    togglePaper() {
      this.paperEnabled = !this.paperEnabled;
      this.saveAutomation();
      if (this.paperEnabled) this.runAutomation({ force: true });
    },

    toggleIntentArmed() {
      this.intentArmed = !this.intentArmed;
      this.saveAutomation();
    },

    updatePolicy() {
      this.policy = normalizePolicy(this.policy);
      this.saveAutomation();
    },

    clearJournal() {
      this.paperJournal = [];
      this.tradeIntents = [];
      this.tradeLedger = [];
      this.saveAutomation();
    },

    markLedger(record, outcome) {
      this.tradeLedger = this.tradeLedger.map((item) => {
        if (item.id !== record.id) return item;
        if (outcome === "win") return recordExecutionResult(item, { status: "settled", realized_net_usd: Math.abs(Number(item.expected_net_usd || 0)), detail: "marked win" });
        if (outcome === "loss") return recordExecutionResult(item, { status: "settled", realized_net_usd: -Math.abs(Number(item.expected_net_usd || 0)), detail: "marked loss" });
        return recordExecutionResult(item, { status: "skipped", detail: "marked skipped" });
      });
      this.saveAutomation();
    },

    mergeLedger(records) {
      const seen = new Set();
      const merged = [];
      for (const record of normalizeLedger(records)) {
        const key = `${record.type}:${record.opportunity_id}:${record.created_at}`;
        if (seen.has(key)) continue;
        seen.add(key);
        merged.push(record);
      }
      return merged.slice(0, 100);
    },

    notifySignals(signals) {
      const fresh = signals.filter((signal) => signal.notify && !this.seenSignalIds.has(signal.id));
      for (const signal of fresh) this.seenSignalIds.add(signal.id);
      if (!fresh.length || !("Notification" in window)) return;
      if (Notification.permission === "default") Notification.requestPermission().catch(() => {});
      if (Notification.permission !== "granted") return;
      for (const signal of fresh.slice(0, 3)) {
        new Notification(`NASE ${signal.pair}`, {
          body: `${this.formatPercent(signal.spread_pct)} spread, confidence ${signal.confidence.toFixed(0)}, ${signal.executable_related_quotes} executable checks`,
        });
      }
    },

    get topOpportunities() {
      return (this.snapshot?.opportunities || []).slice(0, 8);
    },

    get actionableSignals() {
      return this.scoutSignals.filter((signal) => signal.status !== "blocked").slice(0, 6);
    },

    get ledgerSummary() {
      return summarizeLedger(this.tradeLedger);
    },

    get statusLabel() {
      if (this.snapshot?.busy) return "refreshing";
      if (this.snapshot?.error) return "error";
      return `cycle ${this.snapshot?.cycle || 0}`;
    },

    get snapshotAgeLabel() {
      if (!this.snapshot?.updated_at) return "Waiting for tracker data.";
      const date = new Date(this.snapshot.updated_at);
      return `Updated ${date.toLocaleTimeString()}; collection took ${Number(this.snapshot.elapsed_seconds || 0).toFixed(1)}s.`;
    },

    formatNumber(value) {
      return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(Number(value || 0));
    },

    formatMoney(value) {
      return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(Number(value || 0));
    },

    formatPercent(value) {
      return `${Number(value || 0).toFixed(3)}%`;
    },

    signalTone(signal) {
      if (signal.status === "actionable") return "is-good";
      if (signal.status === "review") return "is-warn";
      return "is-bad";
    },

    sourceTone(source) {
      if (source.circuit_open || !source.healthy) return "is-bad";
      if (source.rate_limited) return "is-warn";
      return "is-good";
    },

    sourceLabel(source) {
      if (source.circuit_open) return `backoff ${Number(source.wait || 0).toFixed(0)}s`;
      if (source.rate_limited) return `wait ${Number(source.wait || 0).toFixed(0)}s`;
      return `${this.formatNumber(source.normalized)} norm / ${this.formatNumber(source.executable)} exec`;
    },

    openNaseDashboard() {
      window.open(dashboardUrl, "_blank", "noopener,noreferrer");
    },

    async copyPrompt(prompt) {
      this.copyStatus = "";
      try {
        await navigator.clipboard.writeText(prompt);
        this.copyStatus = "Prompt copied.";
      } catch {
        this.copyStatus = prompt;
      }
    },
  });
}

if (globalThis.Alpine) {
  installStore();
} else {
  document.addEventListener("alpine:init", installStore, { once: true });
}
