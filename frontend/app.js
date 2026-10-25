/* Fleet Reliability Explorer: a dependency-free single-page app over the explorer API.
 *
 * Views (hash routes):
 *   #/                              home: counts, suggested starting points
 *   #/entity?iri=...                relationship explorer: graph, related information, details
 *   #/list/<type>?offset=0          paged list of aircraft, defects, work orders, removals, ...
 *   #/questions[/cq03?param=...]    the ten competency questions, runnable with parameters
 *   #/ask?q=...                     natural-language search (Amazon Bedrock), when enabled
 *
 * No third-party scripts: the graph is drawn with plain SVG, so the page works under a strict
 * Content-Security-Policy (script-src 'self') and needs nothing from a CDN.
 */
"use strict";

const ID_BASE = "https://fleet.example.com/id/";
const TYPES = {
  aircraft:   { label: "Aircraft",                plural: "Aircraft",       path: "aircraft",   color: "#1b3a6b" },
  defect:     { label: "Defect",                  plural: "Defects",        path: "defect",     color: "#c2410c" },
  workOrder:  { label: "Work Order",              plural: "Work Orders",    path: "work-order", color: "#2b78c5" },
  deferral:   { label: "MEL Deferral",            plural: "MEL Deferrals",  path: "deferral",   color: "#b7791f" },
  removal:    { label: "Component Removal",       plural: "Removals",       path: "removal",    color: "#7c3aed" },
  component:  { label: "Component",               plural: "Components",     path: "component",  color: "#0f766e" },
  part:       { label: "Part",                    plural: "Parts",          path: "part",       color: "#92400e" },
  vendor:     { label: "Vendor",                  plural: "Vendors",        path: "vendor",     color: "#b5523b" },
  station:    { label: "Station",                 plural: "Stations",       path: "station",    color: "#5a4fcf" },
  flight:     { label: "Flight",                  plural: "Flights",        path: "flight",     color: "#0369a1" },
  directive:  { label: "Airworthiness Directive", plural: "Directives",     path: "directive",  color: "#be123c" },
  ataChapter: { label: "ATA Chapter",             plural: "ATA Chapters",   path: "ata",        color: "#6d8a24" },
};
// Result columns that hold a business key, and the entity type they identify.
const KEY_COLUMNS = {
  tailNumber: "aircraft", installedOn: "aircraft", defectNumber: "defect", workOrderNumber: "workOrder",
  correctedBy: "workOrder", deferralNumber: "deferral", removalNumber: "removal",
  serialNumber: "component", partNumber: "part", vendorCode: "vendor", stationCode: "station",
  homeBase: "station", flightLegId: "flight", adNumber: "directive", ataCode: "ataChapter",
};
// Columns that mix record types (Tail 360's "item"): recognize the key by its format.
const KEY_PATTERNS = [[/^DF-\d{6}$/, "defect"], [/^WO-\d{7}$/, "workOrder"], [/^MEL-\d{6}$/, "deferral"],
  [/^RM-\d{6}$/, "removal"], [/^AD-\d{4}-\d{2}-\d{2}$/, "directive"], [/^N\d{3}[A-Z]{2}$/, "aircraft"],
  [/^[A-Z]{2}\d{5}$/, "component"]];
const MONEY = new Set(["unitCost"]);
const BARS = { repeatPct: 100, noFaultFoundPct: 100, per1000Departures: 1, meanHoursToRemoval: 8000 };
const HEADERS = {
  ataCode: "ATA", melItem: "MEL item", melCategory: "MEL cat.", per1000Departures: "Per 1,000 departures",
  noFaultFoundPct: "No fault found %", repeatPct: "Repeat %", iri: "IRI",
};

const state = { config: { apiBase: "/api", nlqEnabled: false, environment: "local" }, stats: null, questions: null };
const view = document.getElementById("view");

/* ------------------------------------------------------------------ helpers */

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

const SVG_NS = "http://www.w3.org/2000/svg";
function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined) continue;
    if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat(Infinity)) if (c) node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return node;
}

function iriFor(type, id) { return ID_BASE + TYPES[type].path + "/" + encodeURIComponent(id); }
function typeOfIri(iri) {
  const path = (iri || "").slice(ID_BASE.length).split("/")[0];
  return Object.keys(TYPES).find((k) => TYPES[k].path === path);
}
function entityHref(iri) { return "#/entity?iri=" + encodeURIComponent(iri); }
function humanize(name) {
  if (HEADERS[name]) return HEADERS[name];
  const s = name.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}
function fmt(col, v) {
  if (v === null || v === undefined || v === "") return "";
  if (MONEY.has(col) && typeof v === "number") return "$" + v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (typeof v === "number" && /year/i.test(col)) return String(v);
  if (typeof v === "number") return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return String(v);
}
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }

async function api(path, params) {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  const resp = await fetch(state.config.apiBase + path + qs, { headers: { Accept: "application/json" } });
  const body = await resp.json().catch(() => ({ error: resp.statusText }));
  if (!resp.ok) throw new Error(body.error || resp.statusText);
  return body;
}

function loading(msg = "Loading…") { return el("div", { class: "loading" }, el("span", { class: "spinner" }), msg); }
function errorBox(err) { return el("div", { class: "error" }, "Something went wrong: ", String(err.message || err)); }

/* ------------------------------------------------------------------ icons */

const ICONS = {
  aircraft: [["path", { d: "M12 2.5c.9 0 1.4 1 1.4 2.3v4.6l7.6 4.4v2l-7.6-2.3v4.6l2.2 1.7v1.6L12 20.4l-3.6 1v-1.6l2.2-1.7v-4.6L3 15.8v-2l7.6-4.4V4.8c0-1.3.5-2.3 1.4-2.3z" }]],
  defect: [["path", { d: "M12 3.5l9 16H3z M12 9.5v4.5 M12 16.8v.2" }]],
  workOrder: [["path", { d: "M14.7 6.3a4 4 0 0 0-5.4 5.1L3.5 17.2a1.9 1.9 0 0 0 2.7 2.7l5.8-5.8a4 4 0 0 0 5.1-5.4l-2.4 2.4-2.2-.6-.6-2.2z" }]],
  deferral: [["circle", { cx: 12, cy: 12.5, r: 8.5 }], ["path", { d: "M12 7.5v5l3.2 2 M9.5 2.5h5" }]],
  removal: [["path", { d: "M4 10h16v10H4z M8 10V7.5h8V10 M12 3v9 M9 6l3-3 3 3" }]],
  component: [["path", { d: "M12 2.8l8 4.6v9.2l-8 4.6-8-4.6V7.4z M12 12l8-4.6 M12 12v9.2 M12 12L4 7.4" }]],
  vendor: [["path", { d: "M3 21V11.5l5 3v-3l5 3v-3l5 3V4.5h3V21z M2.5 21h19 M7 18h1.5 M11.5 18H13 M16 18h1.5" }]],
  station: [["path", { d: "M9 21l1.2-11h3.6L15 21 M7.5 10h9 M8.5 6.5h7L17 10H7z M12 3v3.5 M6 21h12" }]],
  flight: [["path", { d: "M2.5 19.5h19 M5 15.5l13.7-6.2c1.2-.5 2.4.2 2.1 1-.2.5-.8.9-1.4 1.2L6.8 17.4 3.6 13l1.6-.6 2.3 1.8 3.4-1.6L6.2 6.8l2-.8 6.5 4.6" }]],
  directive: [["path", { d: "M12 2.8l7.5 3v5.4c0 4.8-3.3 8.6-7.5 10-4.2-1.4-7.5-5.2-7.5-10V5.8z M12 8v4.5 M12 15.5v.2" }]],
  part: [["circle", { cx: 12, cy: 12, r: 5 }], ["circle", { cx: 12, cy: 12, r: 1.8 }],
         ["path", { d: "M12 2.5v3.2 M12 18.3v3.2 M2.5 12h3.2 M18.3 12h3.2 M5.3 5.3l2.2 2.2 M16.5 16.5l2.2 2.2 M5.3 18.7l2.2-2.2 M16.5 7.5l2.2-2.2" }]],
  ataChapter: [["path", { d: "M3.5 12.2V3.5h8.7l9 9-8.7 8.7z" }], ["circle", { cx: 8, cy: 8, r: 1.6 }]],
  search: [["circle", { cx: 10.5, cy: 10.5, r: 6.5 }], ["path", { d: "M15.5 15.5L21 21" }]],
  questions: [["circle", { cx: 12, cy: 12, r: 9 }], ["path", { d: "M9.3 9.3a2.8 2.8 0 1 1 3.9 2.6c-.8.4-1.2 1-1.2 1.8v.8 M12 17.2v.3" }]],
  ask: [["path", { d: "M4 5h16v11H9.5L4 20z M8.5 10.5h.1 M12 10.5h.1 M15.5 10.5h.1" }]],
};
function icon(name, attrs = {}) {
  const g = svg("svg", { viewBox: "0 0 24 24", class: "icon", "aria-hidden": "true", ...attrs });
  for (const [tag, a] of ICONS[name] || []) g.append(svg(tag, a));
  return g;
}
document.querySelectorAll("[data-icon]").forEach((n) => n.append(icon(n.dataset.icon)));

/* ------------------------------------------------------------------ tables */

function keyType(col, value) {
  if (KEY_COLUMNS[col]) return KEY_COLUMNS[col];
  if (typeof value !== "string") return null;
  const hit = KEY_PATTERNS.find(([re]) => re.test(value));
  return hit ? hit[1] : null;
}

function cellFor(col, value) {
  const td = el("td");
  const t = keyType(col, value);
  if (t && value) {
    td.append(el("a", { href: entityHref(iriFor(t, value)) }, String(value)));
  } else if (BARS[col] !== undefined && typeof value === "number") {
    const bar = el("span", { class: "bar" });
    bar.style.width = Math.max(2, Math.min(100, (value / BARS[col]) * 100)) + "%";
    td.append(el("div", { class: "bar-cell" }, el("div", { class: "bar-track" }, bar), el("span", {}, fmt(col, value))));
    td.className = "num";
  } else {
    td.append(fmt(col, value));
    if (typeof value === "number") td.className = "num";
    else if (/^\d{4}-\d{2}-\d{2}$/.test(String(value))) td.className = "nowrap";
  }
  return td;
}

function table(columns, rows, { onRow } = {}) {
  if (!rows.length) return el("div", { class: "empty" }, "No rows.");
  const head = el("tr", {}, columns.map((c) => el("th", {}, humanize(c))));
  const body = rows.map((r) => {
    const tr = el("tr", onRow ? { class: "clickable", onclick: (e) => { if (e.target.tagName !== "A") onRow(r); } } : {},
      columns.map((c) => cellFor(c, r[c])));
    return tr;
  });
  return el("div", { class: "table-wrap" }, el("table", {}, el("thead", {}, head), el("tbody", {}, body)));
}

/* ------------------------------------------------------------------ graph */

function wrapLabel(text, max = 22) {
  const s = String(text || "");
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}

function drawGraph(host, data) {
  clear(host);
  const W = Math.max(host.clientWidth, 520);
  const H = Math.max(440, Math.min(data.nodes.some((n) => n.hop) ? 640 : 600, W * 0.7));
  const deepest = Math.max(1, ...data.nodes.map((n) => n.hop || 1));
  const cx = deepest > 2 ? W * 0.36 : W / 2, cy = H / 2;
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "graph", role: "img",
                            "aria-label": `Relationships of ${data.center.label}` });
  const center = data.nodes.find((n) => n.center);
  const ring1 = data.nodes.filter((n) => !n.center && !n.hop);
  const outer = data.nodes.filter((n) => n.hop >= 2);
  const pos = new Map([[center.iri, { x: cx, y: cy }]]);
  const r1 = Math.min(W, H) * (outer.length ? (Math.max(...outer.map((n) => n.hop)) > 2 ? 0.24 : 0.31) : 0.37);
  const stretch = Math.min(1.7, W / H);                   // use the width: an ellipse, not a circle
  const many = ring1.length > 12;
  // Slots around the center; nodes that lead to further hops get the slots nearest the
  // horizontal (rightmost first), where there is room for the chain to continue.
  const slots = ring1.map((_, i) => -Math.PI / 2 + (2 * Math.PI * i) / Math.max(ring1.length, 1));
  const parents = new Set(data.edges.filter((e) => e.hop >= 2).map((e) => e.source));
  const bySide = slots.map((a, i) => i).sort((x, y) =>
    (Math.abs(Math.sin(slots[x])) - (Math.cos(slots[x]) > 0 ? 0.01 : 0)) -
    (Math.abs(Math.sin(slots[y])) - (Math.cos(slots[y]) > 0 ? 0.01 : 0)));
  const order = [...ring1.filter((n) => parents.has(n.iri)), ...ring1.filter((n) => !parents.has(n.iri))];
  const assigned = new Map();
  const free = [...bySide];
  order.filter((n) => parents.has(n.iri)).forEach((n) => assigned.set(n.iri, free.shift()));
  order.filter((n) => !parents.has(n.iri)).forEach((n) => assigned.set(n.iri, free.sort((x, y) => x - y).shift()));
  ring1.forEach((n) => {
    const i = assigned.get(n.iri);
    const a = slots[i];
    const r = many && i % 2 ? r1 * 1.18 : r1 * 0.95;
    pos.set(n.iri, { x: cx + Math.cos(a) * r * stretch, y: cy + Math.sin(a) * r, a });
  });
  // Outer hops continue outward from their parent, fanned out when a parent has several.
  const maxHop = outer.length ? Math.max(...outer.map((n) => n.hop)) : 1;
  for (let hop = 2; hop <= maxHop; hop++) {
    const children = new Map();
    outer.filter((n) => n.hop === hop).forEach((n) => {
      const edge = data.edges.find((e) => e.target === n.iri && e.hop === hop);
      if (edge && pos.get(edge.source)) {
        if (!children.has(edge.source)) children.set(edge.source, []);
        children.get(edge.source).push(n);
      }
    });
    for (const [parentIri, kids] of children) {
      const parent = pos.get(parentIri);
      kids.forEach((n, k) => {
        // Lean toward the horizontal: there is more room left and right than above and below.
        const side = Math.cos(parent.a) >= 0 ? 0 : Math.PI;
        const lean = parent.a + (side - (parent.a > Math.PI ? parent.a - 2 * Math.PI : parent.a)) * 0.35;
        const a = lean + (k - (kids.length - 1) / 2) * (hop > 2 ? 1.3 : 0.55);
        const room = Math.max(90, (W - 80 - parent.x) / Math.max(1, deepest - hop + 1));
        const d = Math.min(Math.min(W, H) * 0.2 * stretch, Math.cos(a) > 0.3 ? room : Infinity);
        pos.set(n.iri, { x: parent.x + Math.cos(a) * d, y: parent.y + Math.sin(a) * d / stretch, a });
      });
    }
  }
  for (const p of pos.values()) {   // keep everything inside the canvas
    p.x = Math.max(70, Math.min(W - 70, p.x));
    p.y = Math.max(p.y < cy - 20 ? 96 : 56, Math.min(H - 62, p.y));
  }

  const edges = svg("g", { class: "edges" });
  const labels = svg("g", { class: "edge-labels" });
  const perPredicate = {};
  data.edges.forEach((e) => { perPredicate[e.predicate] = (perPredicate[e.predicate] || 0) + 1; });
  const labelled = new Set();
  data.edges.forEach((e) => {
    const a = pos.get(e.source), b = pos.get(e.target);
    if (!a || !b) return;
    edges.append(svg("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: e.hop >= 2 ? "edge hop2" : "edge" }));
    // Repeated relationships (a part's 12 units) get one label, not twelve.
    if (perPredicate[e.predicate] <= 2 || !labelled.has(e.predicate)) {
      labelled.add(e.predicate);
      const t = e.source === center.iri ? 0.6 : 0.5;     // nearer the neighbor, away from the center label
      labels.append(svg("text", { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t - 3, class: "edge-label",
                                  "text-anchor": "middle" }, e.label));
    }
  });
  root.append(edges, labels);

  const nodes = svg("g", { class: "nodes" });
  data.nodes.forEach((n) => {
    const p = pos.get(n.iri);
    if (!p) return;
    const r = n.center ? 38 : n.hop ? 20 : 25;
    const color = (TYPES[n.type] || {}).color || "#475569";
    const g = svg("g", { class: "node" + (n.center ? " center" : ""), transform: `translate(${p.x},${p.y})`,
                         tabindex: 0, role: "link",
                         onclick: () => { if (!n.center) location.hash = entityHref(n.iri); },
                         onkeydown: (ev) => { if (ev.key === "Enter" && !n.center) location.hash = entityHref(n.iri); } },
      svg("title", {}, `${n.typeLabel}: ${n.label} (${n.identifier})`),
      svg("circle", { r, fill: color, class: "node-disc" }));
    const ic = icon(n.type, { x: -r * 0.55, y: -r * 0.55, width: r * 1.1, height: r * 1.1, class: "node-icon" });
    g.append(ic);
    // Labels go below the node, except for nodes in the upper part of the canvas, where the
    // edge arrives from below: there they go above so the line never crosses the text.
    const above = !n.center && p.y < cy - 20;
    const hasId = n.label !== n.identifier && !String(n.label).includes(n.identifier);
    const y0 = above ? -r - (hasId ? 38 : 24) : r + 14;
    g.append(svg("text", { y: y0, "text-anchor": "middle", class: "node-type" }, n.typeLabel),
             svg("text", { y: y0 + 15, "text-anchor": "middle", class: "node-label" },
                 wrapLabel(n.label, n.center ? 30 : 24)));
    if (hasId) {
      g.append(svg("text", { y: y0 + 29, "text-anchor": "middle", class: "node-id" }, wrapLabel(n.identifier, 24)));
    }
    nodes.append(g);
  });
  root.append(nodes);
  host.append(root);
}

/* ------------------------------------------------------------------ views */

async function viewHome() {
  const stats = state.stats || (state.stats = await api("/stats"));
  const cards = ["aircraft", "defect", "workOrder", "deferral", "removal", "component", "flight"].map((t) =>
    el("a", { class: "stat", href: "#/list/" + t },
      el("span", { class: "stat-ico" }, icon(t)),
      el("span", { class: "stat-n" }, (stats.counts[t] || 0).toLocaleString()),
      el("span", { class: "stat-l" }, TYPES[t].plural)));
  const starts = [
    ["Start with defect DF-100245", "A bleed trip on N812BB at MDW. Follow it to the deferral, the work order, the unit removed and the shop that last repaired it.", entityHref(iriFor("defect", "DF-100245"))],
    ["Which units are rogue?", "CQ03 finds serial numbers that keep coming off aircraft after a few hundred hours, often with no fault found.", "#/questions/cq03"],
    ["Which shop is behind them?", "CQ05 compares repair shops on hours flown before the next unscheduled removal.", "#/questions/cq05"],
    ["Who is flying with them now?", "CQ10 lists the tails carrying units from that shop, for a targeted removal campaign.", "#/questions/cq10"],
  ];
  return el("section", { class: "home" },
    el("div", { class: "hero" },
      el("p", { class: "eyebrow" }, "From disconnected data to connected insights"),
      el("h1", {}, "See how defects, components, shops and flights connect"),
      el("p", { class: "lede" }, "Every record here is a node in one knowledge graph that follows the fleet reliability ontology. ",
        "Search for a tail, defect, serial number, part, vendor or station, then follow the relationships.")),
    el("div", { class: "stats" }, cards),
    el("p", { class: "stat-foot" }, `${stats.triples.toLocaleString()} triples · ${Number(stats.delayMinutes).toLocaleString()} delay minutes and ${stats.cancellations} cancellations caused by maintenance`),
    el("h2", {}, "Good places to start"),
    el("div", { class: "starts" }, starts.map(([t, d, href]) =>
      el("a", { class: "start", href }, el("strong", {}, t), el("span", {}, d), el("span", { class: "go" }, "Open →")))));
}

function panelRows(rows) {
  return el("dl", { class: "panel-rows" }, rows.filter((r) => r.value !== undefined && r.value !== null && r.value !== "")
    .map((r) => [el("dt", {}, r.label), el("dd", {}, fmt(r.key || "", r.value))]));
}

async function viewEntity(params) {
  const iri = params.get("iri");
  const type = typeOfIri(iri);
  const graphHost = el("div", { class: "graph-host" }, loading("Loading relationships…"));
  const side = el("aside", { class: "panel" }, loading());
  const details = el("section", { class: "details" });
  const head = el("div", { class: "entity-head" });
  const page = el("section", { class: "explore" }, head, el("div", { class: "explore-grid" },
    el("div", { class: "graph-card" }, graphHost, el("div", { class: "legend" },
      Object.entries(TYPES).map(([k, t]) => { const dot = el("span", { class: "dot" }); dot.style.background = t.color; return el("span", {}, dot, t.label); }))),
    side), details);

  (async () => {
    try {
      const data = await api("/neighborhood", { iri });
      const c = data.center;
      head.append(el("span", { class: "chip" }, icon(c.type), c.typeLabel),
                  el("h1", {}, c.identifier));
      if (c.label !== c.identifier) head.append(el("span", { class: "sub" }, c.label));
      drawGraph(graphHost, data);
      window.addEventListener("resize", () => drawGraph(graphHost, data), { once: true });
      details.append(el("h2", {}, "Details"),
        el("div", { class: "attr-grid" }, c.attributes.map((a) =>
          el("div", { class: "attr" }, el("span", { class: "attr-l" }, humanize(a.property)), el("span", { class: "attr-v" }, fmt(a.property, a.value))))),
        el("p", { class: "classes" }, "Types (with inferred superclasses): ", c.classes.join(" · ")));
      if (type !== "defect") {
        clear(side).append(el("h2", {}, "Related Information"), panelRows([
          ...c.attributes.slice(1, 6).map((a) => ({ label: humanize(a.property), value: a.value, key: a.property })),
          ...data.relations.map((r) => ({ label: r.label.charAt(0).toUpperCase() + r.label.slice(1), value: r.total })),
        ]));
        const big = data.relations.filter((r) => r.total > r.shown);
        if (big.length) side.append(el("p", { class: "note" }, big.map((r) => `Graph shows ${r.shown} of ${r.total} “${r.label}”.`).join(" ")));
      }
    } catch (err) { clear(graphHost).append(errorBox(err)); }
  })();

  if (type === "defect") {
    (async () => {
      try {
        const rel = await api("/related", { iri });
        const hist = rel.sameChapterHistory;
        const btn = el("button", { class: "primary", type: "button" },
          `View ${hist.length} defects in this chapter on ${rel.defect.tailNumber} →`);
        const relHost = el("div");
        btn.addEventListener("click", () => {
          clear(relHost).append(el("h2", { id: "related" }, `${rel.defect.chapter} on ${rel.defect.tailNumber}`),
            el("p", { class: "muted" }, "The aircraft's history in the same ATA chapter. Three or more in ten days is a repeat defect (CQ02)."),
            table(["defectNumber", "reportedDate", "station", "description", "status", "correctedBy"], hist));
          relHost.scrollIntoView({ behavior: "smooth" });
        });
        clear(side).append(el("h2", {}, "Related Information"),
          panelRows(rel.panel.map((r) => ({ ...r, key: r.label }))), btn);
        details.after(relHost);
      } catch (err) { clear(side).append(errorBox(err)); }
    })();
  }
  return page;
}

async function viewList(type, params) {
  const offset = Number(params.get("offset") || 0);
  const data = await api("/entities", { type, offset, limit: 50 });
  const pager = el("div", { class: "pager" },
    el("span", {}, `${offset + 1}–${Math.min(offset + data.rows.length, data.total)} of ${data.total.toLocaleString()}`),
    el("a", { class: "btn" + (offset === 0 ? " disabled" : ""), href: `#/list/${type}?offset=${Math.max(0, offset - 50)}` }, "← Previous"),
    el("a", { class: "btn" + (offset + 50 >= data.total ? " disabled" : ""), href: `#/list/${type}?offset=${offset + 50}` }, "Next →"));
  return el("section", { class: "list" },
    el("div", { class: "list-head" }, el("h1", {}, icon(type), TYPES[type].plural), pager),
    table(data.columns, data.rows, { onRow: (r) => { location.hash = entityHref(r.iri); } }));
}

async function viewQuestions(id, params) {
  const qs = state.questions || (state.questions = await api("/competency"));
  const current = qs.find((q) => q.id === id) || qs[0];
  const list = el("ol", { class: "cq-list" }, qs.map((q) =>
    el("li", { class: q.id === current.id ? "active" : "" },
      el("a", { href: "#/questions/" + q.id }, el("span", { class: "cq-id" }, q.id.toUpperCase()), q.title))));
  const form = el("form", { class: "cq-form" });
  current.params.forEach((p) => {
    form.append(el("label", {}, humanize(p.name),
      el("input", { name: p.name, value: params.get(p.name) || p.default, pattern: p.pattern.replace(/^\^|\$$/g, ""), required: true })));
  });
  const out = el("div", { class: "cq-out" });
  const run = async () => {
    clear(out).append(loading("Running SPARQL…"));
    const values = Object.fromEntries(new FormData(form).entries());
    try {
      const r = await api("/competency/" + current.id, values);
      clear(out).append(
        el("div", { class: "cq-meta" }, `${r.rows.length} rows · ${r.elapsedMs} ms`),
        table(r.columns, r.rows),
        el("details", { class: "sparql" }, el("summary", {}, "SPARQL"), el("pre", {}, el("code", {}, r.sparql))));
    } catch (err) { clear(out).append(errorBox(err)); }
  };
  form.append(el("button", { class: "primary", type: "submit" }, "Run question"));
  form.addEventListener("submit", (e) => { e.preventDefault(); run(); });
  run();
  return el("section", { class: "questions" },
    el("div", { class: "cq-side" }, el("h2", {}, "Competency questions"),
      el("p", { class: "muted" }, "The business questions the ontology and graph must answer. Each is a SPARQL file in queries/competency/."), list),
    el("div", { class: "cq-main" },
      el("p", { class: "eyebrow" }, current.id.toUpperCase()),
      el("h1", {}, current.title),
      el("p", { class: "question" }, current.question),
      el("p", { class: "value" }, el("strong", {}, "Why it matters: "), current.value),
      form, out));
}

async function viewAsk(params) {
  const q = params.get("q") || "";
  const examples = ["Which stations had the most bleed trip defects?",
    "What is the average delay caused by ATA 36 defects by aircraft model?",
    "Which vendors repaired units that were removed within 500 flight hours?",
    "List open deferrals on 737 MAX 8 aircraft"];
  const input = el("textarea", { rows: 2, placeholder: "Ask a question about fleet reliability…" });
  input.value = q;
  const out = el("div", { class: "ask-out" });
  const ask = async () => {
    const question = input.value.trim();
    if (question.length < 3) return;
    history.replaceState(null, "", "#/ask?q=" + encodeURIComponent(question));
    clear(out).append(loading("Writing and running a SPARQL query with Amazon Bedrock…"));
    try {
      const resp = await fetch(state.config.apiBase + "/nlq", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) });
      const r = await resp.json();
      if (!resp.ok) throw new Error(r.error || resp.statusText);
      const cols = r.rows && r.rows.length ? Object.keys(r.rows.reduce((a, row) => Object.assign(a, row), {})) : [];
      clear(out).append(
        r.error ? errorBox(new Error(r.error)) : el("p", { class: "answer" }, r.answer || `${r.rows.length} rows.`),
        r.explanation ? el("p", { class: "muted" }, r.explanation) : null,
        r.rows && r.rows.length ? table(cols, r.rows) : null,
        el("details", { class: "sparql", open: !!r.error }, el("summary", {}, "Generated SPARQL"), el("pre", {}, el("code", {}, r.sparql || ""))),
        el("p", { class: "fine" }, `Model: ${r.model}. Queries are read-only and checked before they run.`));
    } catch (err) { clear(out).append(errorBox(err)); }
  };
  const disabled = !state.config.nlqEnabled;
  const page = el("section", { class: "ask" },
    el("p", { class: "eyebrow" }, "Natural language search · Amazon Bedrock"),
    el("h1", {}, "Ask a question"),
    disabled ? el("div", { class: "notice" }, state.config.environment === "local"
      ? "Natural-language search is off in local mode. Run scripts/serve_local.py --bedrock with AWS credentials that can call Amazon Bedrock."
      : "Natural-language search is not deployed. Deploy with -c nlq=true.") : null,
    el("form", { class: "ask-form", onsubmit: (e) => { e.preventDefault(); ask(); } }, input,
      el("button", { class: "primary", type: "submit", disabled }, "Ask")),
    el("div", { class: "chips" }, examples.map((x) => el("button", { type: "button", class: "chip-btn", disabled,
      onclick: () => { input.value = x; ask(); } }, x))),
    out);
  if (q && !disabled) ask();
  return page;
}

/* ------------------------------------------------------------------ search box */

const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("search-input");
const searchResults = document.getElementById("search-results");
let searchTimer = null, searchSeq = 0;

function looksLikeQuestion(text) { return text.trim().split(/\s+/).length >= 4 || /\?$/.test(text.trim()); }

async function runSearch() {
  const text = searchInput.value.trim();
  const seq = ++searchSeq;
  if (text.length < 2) { searchResults.hidden = true; return; }
  const items = [];
  if (state.config.nlqEnabled && looksLikeQuestion(text)) {
    items.push(el("a", { class: "sr ask-item", href: "#/ask?q=" + encodeURIComponent(text), role: "option" },
      icon("ask"), el("span", {}, el("strong", {}, "Ask: "), text)));
  }
  try {
    const r = await api("/search", { q: text });
    if (seq !== searchSeq) return;
    r.results.forEach((h) => items.push(el("a", { class: "sr", href: entityHref(h.iri), role: "option" },
      el("span", { class: "sr-ico" }, icon(h.type)),
      el("span", { class: "sr-main" }, el("strong", {}, h.identifier),
        el("small", {}, h.typeLabel + (h.label !== h.identifier ? " · " + h.label : ""))))));
  } catch (err) { /* keep the ask item */ }
  clear(searchResults).append(...(items.length ? items : [el("div", { class: "sr empty" }, "No matches")]));
  searchResults.hidden = false;
}
searchInput.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(runSearch, 220); });
searchInput.addEventListener("focus", () => { if (searchResults.childElementCount) searchResults.hidden = false; });
document.addEventListener("click", (e) => { if (!searchForm.contains(e.target)) searchResults.hidden = true; });
searchForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const first = searchResults.querySelector("a.sr:not(.ask-item)") || searchResults.querySelector("a.sr");
  if (!searchResults.hidden && first) { location.hash = first.getAttribute("href"); }
  else if (state.config.nlqEnabled && looksLikeQuestion(searchInput.value)) location.hash = "#/ask?q=" + encodeURIComponent(searchInput.value);
  else { await runSearch(); const f = searchResults.querySelector("a.sr"); if (f) location.hash = f.getAttribute("href"); }
  searchResults.hidden = true;
});
searchResults.addEventListener("click", () => { searchResults.hidden = true; });

/* ------------------------------------------------------------------ router */

async function route() {
  const hash = location.hash.slice(1) || "/";
  const [path, query] = hash.split("?");
  const params = new URLSearchParams(query || "");
  const parts = path.split("/").filter(Boolean);
  const section = parts[0] === "list" ? parts[1] : parts[0] === "entity" ? typeOfIri(params.get("iri")) : parts[0] || "home";
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === section));
  clear(view).append(loading());
  try {
    let node;
    if (parts[0] === "entity") node = await viewEntity(params);
    else if (parts[0] === "list" && TYPES[parts[1]]) node = await viewList(parts[1], params);
    else if (parts[0] === "questions") node = await viewQuestions(parts[1], params);
    else if (parts[0] === "ask") node = await viewAsk(params);
    else node = await viewHome();
    clear(view).append(node);
    view.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  } catch (err) { clear(view).append(errorBox(err)); }
}

(async function start() {
  try {
    const resp = await fetch("config.json", { cache: "no-store" });
    if (resp.ok) Object.assign(state.config, await resp.json());
  } catch (err) { /* defaults */ }
  document.getElementById("env-badge").textContent = state.config.environment === "aws" ? "AWS · Amazon Neptune" : "Local · in-memory graph";
  document.getElementById("nav-ask").classList.toggle("off", !state.config.nlqEnabled);
  window.addEventListener("hashchange", route);
  route();
})();
