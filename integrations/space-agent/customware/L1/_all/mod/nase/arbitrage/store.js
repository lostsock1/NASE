import { dashboardUrl, snapshot, sources as fetchSources } from "./ext/skills/nase-arbitrage/nase.js";

function installStore() {
  const Alpine = globalThis.Alpine;
  if (!Alpine || Alpine.store("naseArbitrage")) return;

  Alpine.store("naseArbitrage", {
    loading: false,
    error: "",
    copyStatus: "",
    snapshot: null,
    summary: {},
    sources: [],

    async init() {
      await this.refresh();
      this.timer = window.setInterval(() => this.refresh({ quiet: true }), 10000);
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

    get topOpportunities() {
      return (this.snapshot?.opportunities || []).slice(0, 8);
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

    formatPercent(value) {
      return `${Number(value || 0).toFixed(3)}%`;
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
    }
  });
}

if (globalThis.Alpine) {
  installStore();
} else {
  document.addEventListener("alpine:init", installStore, { once: true });
}
