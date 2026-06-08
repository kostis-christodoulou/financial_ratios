from __future__ import annotations

import json
import math
from numbers import Real
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd

from finstat.config import Settings
from finstat.db.repositories import FinancialRepository


def run_server(settings: Settings, host: str = "127.0.0.1", port: int = 8000) -> None:
    repo = FinancialRepository(settings)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._html(HTML)
            elif parsed.path == "/api/company":
                ticker = parse_qs(parsed.query).get("ticker", [""])[0]
                self._json(repo.company_overview(ticker))
            elif parsed.path == "/api/companies":
                self._json(repo.companies())
            elif parsed.path == "/api/search":
                query = parse_qs(parsed.query).get("q", [""])[0]
                self._json(repo.search_sec_companies(query))
            elif parsed.path == "/api/ratios":
                ticker = parse_qs(parsed.query).get("ticker", [""])[0]
                self._json(repo.ratio_names(ticker))
            elif parsed.path == "/api/plot":
                query = parse_qs(parsed.query)
                ticker = query.get("ticker", [""])[0]
                ratio = query.get("ratio", ["Net margin"])[0]
                compare = query.get("compare", [None])[0] or None
                start = query.get("start", [None])[0] or None
                end = query.get("end", [None])[0] or None
                self._html(repo.ratio_plot_html(ticker, ratio, start_date=start, end_date=end, compare_ticker_or_cik=compare))
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/refresh":
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                payload = json.loads(body or "{}")
                ticker = payload.get("ticker", "")
                years = payload.get("years")
                company = repo.refresh_company(ticker, years=years, refresh_http=bool(payload.get("refresh_http", False)))
                self._json({"ok": True, **company})
            else:
                self.send_error(404)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _json(self, payload: Any) -> None:
            data = json.dumps(_json_safe(payload), default=str, allow_nan=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _html(self, html: str) -> None:
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Open http://{host}:{port}")
    server.serve_forever()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, bool)):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (AttributeError, TypeError, ValueError):
            pass
    if isinstance(value, Real):
        return value if math.isfinite(float(value)) else None
    return value


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Finstat</title>
  <style>
    :root {
      --bg: #f7f7f4;
      --panel: #ffffff;
      --ink: #1f2328;
      --muted: #69707a;
      --line: #deded8;
      --accent: #2f6f68;
      --amber: #a16207;
      --red: #b42318;
      --green: #166534;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }
    .app { display: grid; grid-template-columns: 280px 1fr; min-height: 100vh; }
    aside { border-right: 1px solid var(--line); background: #fbfbf8; padding: 18px; }
    main { padding: 24px 30px 40px; }
    .brand { font-weight: 720; font-size: 19px; margin-bottom: 18px; }
    .field { display: flex; gap: 8px; margin-bottom: 12px; }
    input, button, select {
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: white;
      color: var(--ink);
      font: inherit;
    }
    input { width: 100%; padding: 0 10px; }
    select { width: 100%; padding: 0 9px; }
    button { padding: 0 11px; cursor: pointer; }
    button.primary { background: var(--accent); color: white; border-color: var(--accent); }
    button:disabled { cursor: wait; opacity: 0.62; }
    .nav { margin-top: 20px; display: grid; gap: 6px; }
    .nav button { text-align: left; background: transparent; border-color: transparent; }
    .nav button.active { background: #e8efed; border-color: #d3e0dd; }
    .topbar { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 18px; }
    h1 { font-size: 28px; margin: 0 0 4px; letter-spacing: 0; }
    .subtle { color: var(--muted); font-size: 13px; }
    .grid { display: grid; grid-template-columns: repeat(4, minmax(160px, 1fr)); gap: 10px; margin: 18px 0; }
    .metric, .section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    .metric .label { color: var(--muted); font-size: 12px; }
    .metric .value { font-size: 22px; font-weight: 700; margin-top: 6px; }
    .tabs { display: flex; gap: 8px; margin: 16px 0; }
    .tabs button.active { background: var(--ink); color: white; border-color: var(--ink); }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { padding: 8px 9px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { color: var(--muted); font-weight: 650; background: #fafaf7; position: sticky; top: 0; }
    .status { margin-top: 10px; min-height: 18px; color: var(--muted); font-size: 13px; }
    .flag-ok { color: var(--green); }
    .flag-missing_component, .flag-zero_denominator { color: var(--amber); }
    .scroll { overflow: auto; max-height: 68vh; }
    .plot-controls {
      display: grid;
      grid-template-columns: 1fr 1fr 1.2fr 1fr 1fr auto;
      gap: 10px;
      align-items: end;
      margin-bottom: 12px;
    }
    .control label { display: block; color: var(--muted); font-size: 12px; margin-bottom: 5px; }
    .plot-frame {
      width: 100%;
      height: 560px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: white;
    }
    @media (max-width: 900px) {
      .app { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      .grid { grid-template-columns: repeat(2, minmax(140px, 1fr)); }
      main { padding: 18px; }
      .plot-controls { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <div class="brand">Finstat</div>
      <div class="field">
        <input id="ticker" placeholder="Company or ticker" aria-label="Company or ticker" list="companySearchOptions" oninput="searchCompanies()" onkeydown="handleTickerKey(event)" />
        <datalist id="companySearchOptions"></datalist>
        <button class="primary" id="searchButton" onclick="searchCompany()">Search</button>
      </div>
      <select id="companyList" aria-label="Loaded companies" onchange="chooseCompany(this.value)"></select>
      <div class="status" id="status"></div>
      <div class="nav">
        <button class="active" onclick="showView('overview', this)">Overview</button>
        <button onclick="showView('statements', this)">Statements</button>
        <button onclick="showView('ratios', this)">Ratios</button>
        <button onclick="showView('plot', this)">Plot</button>
        <button onclick="showView('filings', this)">Filings</button>
      </div>
    </aside>
    <main>
      <div class="topbar">
        <div>
          <h1 id="title">Finstat</h1>
          <div class="subtle" id="meta">No companies loaded</div>
        </div>
        <div class="subtle" id="refreshed"></div>
      </div>
      <div id="overview" class="view"></div>
      <div id="statements" class="view" style="display:none"></div>
      <div id="ratios" class="view" style="display:none"></div>
      <div id="plot" class="view" style="display:none"></div>
      <div id="filings" class="view" style="display:none"></div>
    </main>
  </div>
  <script>
    let current = {};
    let loadedCompanies = [];
    let searchTimer = null;
    function fmtMoney(v) {
      if (v === null || v === undefined || Number.isNaN(Number(v))) return "n/a";
      const n = Number(v);
      const abs = Math.abs(n);
      if (abs >= 1e9) return "$" + (n / 1e9).toFixed(1) + "B";
      if (abs >= 1e6) return "$" + (n / 1e6).toFixed(1) + "M";
      return "$" + n.toLocaleString();
    }
    function fmtRatio(v) {
      if (v === null || v === undefined || Number.isNaN(Number(v))) return "n/a";
      return Number(v).toFixed(3);
    }
    function latestItem(name) {
      return (current.statements || []).find(r => r.canonical_item === name);
    }
    function latestRatio(name) {
      return (current.ratios || []).find(r => r.ratio_name === name && r.quality_flag === "ok")
        || (current.ratios || []).find(r => r.ratio_name === name);
    }
    async function loadCompany(queryOverride) {
      const ticker = (queryOverride || document.getElementById("ticker").value).trim();
      if (!ticker) {
        renderStartState();
        setStatus(loadedCompanies.length ? "Choose a loaded company or search for one." : "No companies loaded.");
        return false;
      }
      setTicker(ticker);
      selectLoadedCompany(ticker.toUpperCase());
      setStatus("Loading " + ticker.toUpperCase() + "...");
      clearMain();
      try {
        const res = await fetch("/api/company?ticker=" + encodeURIComponent(ticker));
        if (!res.ok) throw new Error("Company load failed");
        current = await res.json();
        if (!current.company) {
          renderEmpty(ticker);
          setStatus("No local data yet. Search will add it from EDGAR.");
          return false;
        }
        setTicker(current.company.ticker || ticker);
        selectLoadedCompany(current.company.ticker || ticker);
        render();
        setStatus("Loaded " + (current.company.ticker || ticker) + " from local DuckDB");
        return true;
      } catch (error) {
        renderEmpty(ticker);
        setStatus("Could not load " + ticker + ".");
        return false;
      }
    }
    async function loadCompanies() {
      const res = await fetch("/api/companies");
      loadedCompanies = await res.json();
      const selected = document.getElementById("ticker").value.trim().toUpperCase();
      const placeholder = loadedCompanies.length ? "Loaded companies" : "No companies loaded";
      document.getElementById("companyList").innerHTML =
        `<option value="">${placeholder}</option>` +
        loadedCompanies.map(c => `<option value="${c.ticker}" ${c.ticker === selected ? "selected" : ""}>${c.ticker} · ${c.name}</option>`).join("");
      selectLoadedCompany(selected);
      syncPlotCompanySelectors();
    }
    function chooseCompany(ticker) {
      if (!ticker) return;
      setTicker(ticker);
      loadCompany(ticker);
    }
    function setTicker(ticker) {
      document.getElementById("ticker").value = ticker;
    }
    function selectLoadedCompany(ticker) {
      const list = document.getElementById("companyList");
      if (!list) return;
      list.value = ticker || "";
    }
    function searchCompanies() {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(async () => {
        const query = document.getElementById("ticker").value.trim();
        if (query.length < 2) return;
        const res = await fetch("/api/search?q=" + encodeURIComponent(query));
        const matches = await res.json();
        document.getElementById("companySearchOptions").innerHTML =
          matches.map(c => `<option value="${c.ticker}">${c.ticker} · ${c.name}</option>`).join("");
      }, 180);
    }
    function handleTickerKey(event) {
      if (event.key === "Enter") {
        event.preventDefault();
        searchCompany();
      }
    }
    async function searchCompany() {
      const ticker = document.getElementById("ticker").value.trim();
      if (!ticker) {
        setStatus("Enter a company or ticker first.");
        return;
      }
      const searchButton = document.getElementById("searchButton");
      const wasLoaded = loadedCompanies.some(c => c.ticker === ticker.toUpperCase() || c.name.toLowerCase() === ticker.toLowerCase());
      setStatus((wasLoaded ? "Refreshing " : "Adding ") + ticker.toUpperCase() + " from EDGAR...");
      searchButton.disabled = true;
      clearMain();
      try {
        const res = await fetch("/api/refresh", {method: "POST", body: JSON.stringify({ticker, years:[2024,2025,2026]})});
        if (!res.ok) throw new Error("Refresh failed");
        const refreshed = await res.json();
        const resolvedTicker = refreshed.ticker || ticker;
        setTicker(resolvedTicker);
        await loadCompanies();
        await loadCompany(resolvedTicker);
      } catch (error) {
        renderEmpty(ticker);
        setStatus("Could not search EDGAR for " + ticker + ".");
      } finally {
        searchButton.disabled = false;
      }
    }
    function render() {
      if (!current.company) {
        renderEmpty(document.getElementById("ticker").value.trim() || "company");
        return;
      }
      const c = current.company;
      document.getElementById("title").textContent = `${c.ticker || ""} ${c.name || ""}`.trim();
      document.getElementById("meta").textContent = `CIK ${c.cik} · ${c.exchange || ""} · FY end ${c.fiscal_year_end || ""}`;
      document.getElementById("refreshed").textContent = c.last_refreshed_at ? `Refreshed ${c.last_refreshed_at}` : "";
      renderOverview();
      renderStatements();
      renderRatios();
      renderPlot();
      renderFilings();
    }
    function clearMain() {
      document.getElementById("title").textContent = "";
      document.getElementById("meta").textContent = "";
      document.getElementById("refreshed").textContent = "";
      ["overview", "statements", "ratios", "plot", "filings"].forEach(id => {
        document.getElementById(id).innerHTML = `<div class="section subtle">Loading...</div>`;
      });
    }
    function renderStartState() {
      current = {};
      document.getElementById("title").textContent = "Finstat";
      document.getElementById("meta").textContent = loadedCompanies.length ? "Choose a company" : "No companies loaded";
      document.getElementById("refreshed").textContent = "";
      ["overview", "statements", "ratios", "plot", "filings"].forEach(id => {
        document.getElementById(id).innerHTML = `<div class="section subtle">No local data loaded.</div>`;
      });
    }
    function renderEmpty(query) {
      document.getElementById("title").textContent = query;
      document.getElementById("meta").textContent = "No local data loaded";
      document.getElementById("refreshed").textContent = "";
      ["overview", "statements", "ratios", "plot", "filings"].forEach(id => {
        document.getElementById(id).innerHTML = `<div class="section subtle">No local data for ${query}.</div>`;
      });
    }
    function renderOverview() {
      const metrics = [
        ["Revenue", fmtMoney(latestItem("revenue")?.value)],
        ["Net income", fmtMoney(latestItem("net_income")?.value)],
        ["Cash", fmtMoney(latestItem("cash")?.value)],
        ["Current ratio", fmtRatio(latestRatio("Current ratio")?.value)],
        ["Net margin", fmtRatio(latestRatio("Net margin")?.value)],
        ["FCF margin", fmtRatio(latestRatio("Free cash flow margin")?.value)],
        ["Debt/assets", fmtRatio(latestRatio("Debt to assets")?.value)],
        ["Equity ratio", fmtRatio(latestRatio("Equity ratio")?.value)],
      ];
      document.getElementById("overview").innerHTML = `
        <div class="grid">${metrics.map(m => `<div class="metric"><div class="label">${m[0]}</div><div class="value">${m[1]}</div></div>`).join("")}</div>
        <div class="section"><h2>Recent periods</h2>${table(current.periods || [], ["fiscal_year","fiscal_period","period_end","form"])}</div>`;
    }
    function renderStatements() {
      document.getElementById("statements").innerHTML = `<div class="section scroll">${table(current.statements || [], ["fiscal_year","fiscal_period","period_end","statement","canonical_item","value","tag","quality_flag"])}</div>`;
    }
    function renderRatios() {
      const rows = (current.ratios || []).map(r => {
        const labels = ratioComponentLabels(r.formula_version);
        return {
          ...r,
          numerator_detail: componentDetail(labels[0], r.numerator),
          denominator_detail: componentDetail(labels[1], r.denominator),
        };
      });
      document.getElementById("ratios").innerHTML = `<div class="section scroll">${table(rows, ["fiscal_year","fiscal_period","period_end","ratio_category","ratio_name","value","numerator_detail","denominator_detail","formula_version","quality_flag"])}</div>`;
    }
    function ratioComponentLabels(formulaVersion) {
      const formula = String(formulaVersion || "").replace(/^v\\d+:\\s*/, "");
      const parts = formula.split(" / ");
      if (parts.length < 2) return ["numerator", "denominator"];
      return [parts[0].trim(), parts.slice(1).join(" / ").trim()];
    }
    function componentDetail(label, value) {
      return `${label || "component"} = ${fmtMoney(value)}`;
    }
    function renderPlot() {
      const ratios = [...new Set((current.ratios || []).map(r => r.ratio_name))].sort();
      const dates = [...new Set((current.ratios || []).map(r => String(r.period_end).slice(0, 10)))].sort();
      const preferred = ratios.includes("Net margin") ? "Net margin" : ratios[0] || "";
      const start = dates[0] || "";
      const end = dates[dates.length - 1] || "";
      const primary = current.company?.ticker || document.getElementById("ticker").value.trim().toUpperCase();
      const compareDefault = loadedCompanies.find(c => c.ticker !== primary)?.ticker || "";
      document.getElementById("plot").innerHTML = `
        <div class="section">
          <div class="plot-controls">
            <div class="control">
              <label for="plotPrimary">Company</label>
              <select id="plotPrimary" onchange="syncPrimaryFromPlot()">${companyOptions(primary, false)}</select>
            </div>
            <div class="control">
              <label for="plotCompare">Compare</label>
              <select id="plotCompare" onchange="updatePlot()">${companyOptions(compareDefault, true)}</select>
            </div>
            <div class="control">
              <label for="plotRatio">Ratio</label>
              <select id="plotRatio" onchange="updatePlot()">${ratios.map(r => `<option value="${r}" ${r === preferred ? "selected" : ""}>${r}</option>`).join("")}</select>
            </div>
            <div class="control">
              <label for="plotStart">Start</label>
              <input id="plotStart" type="date" value="${start}" onchange="updatePlot()" />
            </div>
            <div class="control">
              <label for="plotEnd">End</label>
              <input id="plotEnd" type="date" value="${end}" onchange="updatePlot()" />
            </div>
            <button class="primary" onclick="updatePlot()">Plot</button>
          </div>
          <iframe id="plotFrame" class="plot-frame" title="Ratio plot"></iframe>
        </div>`;
      updatePlot();
    }
    function companyOptions(selected, includeNone) {
      const none = includeNone ? `<option value="">No comparison</option>` : "";
      const empty = !includeNone && !loadedCompanies.length ? `<option value="">No companies loaded</option>` : "";
      return none + empty + loadedCompanies.map(c => `<option value="${c.ticker}" ${c.ticker === selected ? "selected" : ""}>${c.ticker} · ${c.name}</option>`).join("");
    }
    function syncPlotCompanySelectors() {
      const primary = document.getElementById("plotPrimary");
      const compare = document.getElementById("plotCompare");
      if (!primary || !compare) return;
      const currentPrimary = primary.value || current.company?.ticker || loadedCompanies[0]?.ticker || "";
      const currentCompare = compare.value;
      primary.innerHTML = companyOptions(currentPrimary, false);
      compare.innerHTML = companyOptions(currentCompare, true);
    }
    function syncPrimaryFromPlot() {
      const selected = document.getElementById("plotPrimary").value;
      if (!selected || selected === current.company?.ticker) return;
      setTicker(selected);
      loadCompany();
    }
    function updatePlot() {
      if (!current.company || !document.getElementById("plotFrame")) return;
      const primary = document.getElementById("plotPrimary").value || current.company.ticker || document.getElementById("ticker").value.trim();
      const compare = document.getElementById("plotCompare").value;
      const params = new URLSearchParams({
        ticker: primary,
        ratio: document.getElementById("plotRatio").value,
        start: document.getElementById("plotStart").value,
        end: document.getElementById("plotEnd").value,
      });
      if (compare && compare !== primary) params.set("compare", compare);
      document.getElementById("plotFrame").src = "/api/plot?" + params.toString();
    }
    function renderFilings() {
      document.getElementById("filings").innerHTML = `<div class="section scroll">${table(current.filings || [], ["form","filing_date","report_date","accession_number","primary_document","source_url"])}</div>`;
    }
    function table(rows, cols) {
      if (!rows.length) return `<div class="subtle">No rows.</div>`;
      return `<table><thead><tr>${cols.map(c => `<th>${headerLabel(c)}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>${cols.map(c => cell(c, r[c])).join("")}</tr>`).join("")}</tbody></table>`;
    }
    function headerLabel(key) {
      const labels = {
        numerator_detail: "numerator",
        denominator_detail: "denominator",
      };
      return labels[key] || key.replaceAll("_", " ");
    }
    function cell(key, value) {
      let v = value;
      if (isDateColumn(key)) v = fmtDate(v);
      if (typeof v === "number" && key === "value") v = Math.abs(v) > 1000 ? fmtMoney(v) : fmtRatio(v);
      if (key === "source_url" && v) v = `<a href="${v}" target="_blank">SEC filing</a>`;
      const cls = key === "quality_flag" ? ` class="flag-${v}"` : "";
      return `<td${cls}>${v ?? ""}</td>`;
    }
    function isDateColumn(key) {
      return key === "period_end" || key === "filing_date" || key === "report_date";
    }
    function fmtDate(value) {
      if (value === null || value === undefined || value === "") return "";
      return String(value).slice(0, 10);
    }
    function showView(id, button) {
      document.querySelectorAll(".view").forEach(el => el.style.display = el.id === id ? "" : "none");
      document.querySelectorAll(".nav button").forEach(el => el.classList.remove("active"));
      button.classList.add("active");
    }
    function setStatus(text) { document.getElementById("status").textContent = text; }
    loadCompanies().then(() => {
      if (loadedCompanies.length) {
        loadCompany(loadedCompanies[0].ticker);
      } else {
        renderStartState();
        setStatus("No companies loaded.");
      }
    });
  </script>
</body>
</html>
"""
