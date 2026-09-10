"use strict";
// SEISMOGRAPH dashboard — vanilla JS, no dependencies.
// Polls GET /v1/weather every POLL_MS ms and renders model status cards.
//
// SG-TRACE: REQ-DASH-001
//   assumption: /v1/weather returns list[ModelWeatherResponse] as JSON
//   test: test_weather_returns_stable_when_no_alerts (backend)
//
// SG-TRACE: REQ-DASH-005
//   assumption: the card is coloured from an EXPLICIT state map, not
//     from "anything that is not DRIFTING is fine" — the previous
//     `status === "DRIFTING" ? drifting : stable` would have painted a
//     STALE leg green while printing the word STALE next to it, which
//     is the same defect DASH-3 fixes on the backend, one layer up
//   test: test_stale_window_is_not_published_as_stable (backend)

const POLL_MS = 60_000;

// Status -> CSS suffix.  An UNKNOWN status the backend may add later
// falls back to "stale" (amber, "no verdict"), never to "stable".
const STATE_CLASS = {
  STABLE: "stable",
  DRIFTING: "drifting",
  STALE: "stale",
};

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function stateOf(entry) {
  return STATE_CLASS[entry && entry.status] || "stale";
}

function fmtTokens(val) {
  if (val === null || val === undefined) return "—";
  return Math.round(Number(val)).toLocaleString() + " tok";
}

function fmtRate(val) {
  if (val === null || val === undefined) return "—";
  return (Number(val) * 100).toFixed(1) + "%";
}

function fmtAge(hours) {
  if (hours === null || hours === undefined) return "no data yet";
  const h = Number(hours);
  if (h < 1) return Math.round(h * 60) + " min ago";
  if (h < 48) return h.toFixed(1) + " h ago";
  return (h / 24).toFixed(1) + " days ago";
}

function fmtTimestamp(ts) {
  if (!ts) return "—";
  try {
    // Backend returns naive UTC; append Z so Date parses as UTC.
    const normalized = ts.endsWith("Z") || ts.includes("+") ? ts : ts + "Z";
    return new Date(normalized).toLocaleString(undefined, {
      dateStyle: "short",
      timeStyle: "medium",
    });
  } catch (_) {
    return String(ts);
  }
}

// ---------------------------------------------------------------------------
// DOM builders
// ---------------------------------------------------------------------------

function buildCard(entry) {
  const state = stateOf(entry);
  const card = document.createElement("div");
  card.className = "card card-" + state;

  // Header row
  const top = document.createElement("div");
  top.className = "card-top";

  const dot = document.createElement("span");
  dot.className = "dot dot-" + state;

  const name = document.createElement("span");
  name.className = "model-name";
  name.textContent = entry.model_tuple;

  const badge = document.createElement("span");
  badge.className = "badge badge-" + state;
  badge.textContent = state === "stale" ? "NO DATA" : entry.status;

  top.appendChild(dot);
  top.appendChild(name);
  top.appendChild(badge);

  // Metrics list.  "Last sample" is always shown: a number without its
  // age is what let a seven-day-dead leg read as healthy.
  const dl = document.createElement("dl");
  dl.className = "metrics";

  const rows = [
    ["Last sample",        fmtAge(entry.window_age_hours),           false],
    ["Avg output length",  fmtTokens(entry.recent_avg_output_length), false],
    ["JSON success rate",  fmtRate(entry.recent_json_success_rate),   false],
  ];
  if (entry.last_alert_timestamp) {
    rows.push(["Last alert", fmtTimestamp(entry.last_alert_timestamp), true]);
  }

  rows.forEach(([label, value, isAlert]) => {
    const row = document.createElement("div");
    row.className = "metric-row" + (isAlert ? " alert-row" : "");

    const dt = document.createElement("dt");
    dt.textContent = label;

    const dd = document.createElement("dd");
    dd.textContent = value;

    row.appendChild(dt);
    row.appendChild(dd);
    dl.appendChild(row);
  });

  card.appendChild(top);
  card.appendChild(dl);

  // A stale card says what it does NOT know, in words.  The metrics
  // above are the leg's LAST reading, not its current one.
  if (state === "stale") {
    const note = document.createElement("p");
    note.className = "card-note";
    note.textContent =
      "This probe has stopped reporting. The figures above are its " +
      "last reading, not a current one — this leg is neither stable " +
      "nor drifting, it is unobserved.";
    card.appendChild(note);
  }

  return card;
}

function buildEmpty() {
  const p = document.createElement("p");
  p.className = "empty";
  p.innerHTML =
    "No probes reporting yet.<br>" +
    "Run a canary probe with <code>probe flush</code> to populate this dashboard.";
  return p;
}

// ---------------------------------------------------------------------------
// Fetch + render
// ---------------------------------------------------------------------------

async function fetchWeather() {
  const r = await fetch("/v1/weather");
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

function setError(msg) {
  const el = document.getElementById("status-banner");
  if (!el) return;
  el.textContent = "⚠️ " + msg;
  el.classList.add("visible");
}

function clearError() {
  const el = document.getElementById("status-banner");
  if (!el) return;
  el.textContent = "";
  el.classList.remove("visible");
}

function setLastUpdated() {
  const el = document.getElementById("last-updated");
  if (!el) return;
  el.textContent = "Updated " + new Date().toLocaleTimeString();
}

async function refresh() {
  const grid = document.getElementById("weather-grid");
  if (!grid) return;
  try {
    const data = await fetchWeather();
    clearError();
    grid.innerHTML = "";
    if (!Array.isArray(data) || data.length === 0) {
      grid.appendChild(buildEmpty());
    } else {
      data.forEach((entry) => grid.appendChild(buildCard(entry)));
    }
    setLastUpdated();
  } catch (err) {
    setError("Could not reach gateway: " + err.message);
  }
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  refresh();
  setInterval(refresh, POLL_MS);
});
