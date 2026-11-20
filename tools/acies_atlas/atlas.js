"use strict";

const one = (selector) => document.querySelector(selector);
const tabs = [...document.querySelectorAll("[data-view]")];
const catalog = one("#catalog");
const search = one("#search");
const sort = one("#sort");
const list = one("#list");
const detail = one("#detail");
const audioFolder = one("#audio-folder");
const audioPlayer = one("#audio-player");
const audio = audioPlayer.querySelector("audio");
const playbackError = one("#playback-error");
const number = new Intl.NumberFormat("en", { maximumFractionDigits: 3 });
const sections = {
  units: ["unit", "units"], runes: ["rune", "runes"], maps: ["map", "maps"],
  music: ["track", "tracks"], sounds: ["sound", "sounds"],
};
const audioTitles = { music: "Music", sounds: "Sound effects" };
const roleNames = {
  base_health: "Health", additional_health: "Additional health", vision: "Vision",
  attack_damage: "Damage", minimum_attack_range: "Min. range", maximum_attack_range: "Max. range",
  attack_speed: "Attack speed", movement_speed: "Movement speed",
};
const operationNames = {
  set: "Set", add: "Add", subtract: "Subtract", multiply: "Multiply by", divide: "Divide by",
  min: "Use the lower value", max: "Use the higher value", compare_register: "Compare register",
  compare_unit_state: "Compare unit state", compare_unit_property: "Compare unit property",
  branch_on_target_match: "Check target filter", branch_on_rune: "Check equipped rune",
  check_unit_asset_condition: "Check unit condition", check_target_force: "Check target force",
  apply_damage_matrix: "Apply damage matrix", jump: "Jump",
};
const initial = { units: "Archer", runes: "Unarmored Defense + Tier 1", maps: "map[003][001][001]" };
const selections = {};
const mobile = matchMedia("(max-width: 670px)");
let data;
let view = "units";
let listScroll = 0;
let audioFiles = new Map();
let playingRecord;
let previewUrl;

function escapeText(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function display(value, unit = "") {
  return value == null
    ? '<span class="empty-value" aria-label="Unavailable">—</span>'
    : escapeText(number.format(value) + unit);
}

function image(record, detailImage = false) {
  if (!record.icon) return detailImage ? "" : '<span class="thumb-empty" aria-hidden="true">—</span>';
  const loading = detailImage ? "" : ' loading="lazy"';
  return `<img alt="" src="${escapeText(record.icon)}"${loading} width="${detailImage ? 83 : 42}" height="${detailImage ? 83 : 42}">`;
}

function coreEntry(record, role) {
  return record.abilities.find((ability) => ability.role === role || ability.name === role);
}

function baseValue(record, role) {
  const assigns = coreEntry(record, role)?.lines.filter((line) => line.operation === "set" && line.destination === "result");
  return assigns?.length === 1 ? assigns[0].source.literal?.value : undefined;
}

function recordMeta(record) {
  if (Object.hasOwn(audioTitles, view)) {
    const maps = record.usage_kind === "Battle music" || record.usage_kind === "Map effect"
      ? record.uses.slice(0, 2).join(", ") : "";
    return [record.artist, maps].filter(Boolean).join(" · ");
  }
  if (view === "units") {
    const armor = data.armor_types[record.stats.armor_type_id.value];
    const attack = data.attack_types[record.stats.attack_type_id.value];
    return [attack, armor].filter(Boolean).join(" · ") || `Unit ${record.id}`;
  }
  if (view === "runes") return record.abilities.slice(0, 3).map((entry) => roleNames[entry.role] || entry.name).join(" · ");
  return `${record.width} × ${record.height} · ${record.id}`;
}

function visibleRecords() {
  const query = search.value.trim().toLocaleLowerCase();
  const result = (data[view] ?? []).filter((record) => {
    const objectives = record.objectives?.map((objective) => objective.text) || [];
    return [record.name, record.id, recordMeta(record), record.symbol, record.engineer, record.album, record.license,
      record.usage_kind, ...(record.uses ?? []), ...objectives]
      .some((value) => value?.toLocaleLowerCase().includes(query));
  });
  if (Object.hasOwn(audioTitles, view)) {
    return result.sort((a, b) => {
      const unidentified = (a.usage_kind === "Unidentified") - (b.usage_kind === "Unidentified");
      return unidentified || a.id.localeCompare(b.id);
    });
  }
  const sortValue = {
    health: (record) => baseValue(record, "base_health"),
    damage: (record) => baseValue(record, "attack_damage"),
    gold: (record) => record.stats.gold_cost.value,
  }[sort.value];
  return result.sort((a, b) => {
    const delta = view === "units" && sortValue ? (sortValue(b) ?? -1) - (sortValue(a) ?? -1) : 0;
    if (delta) return delta;
    if (view === "maps") return b.objectives.length - a.objectives.length || a.id.localeCompare(b.id);
    return a.name.localeCompare(b.name, "en", { numeric: true });
  });
}

function listRow(record) {
  const active = record.id === selections[view];
  const audioView = Object.hasOwn(audioTitles, view);
  const meta = recordMeta(record);
  const identity = `<span class="identity">${audioView ? "" : image(record)}<span class="name">
    <strong>${escapeText(record.name)}</strong>${meta ? `<small>${escapeText(meta)}</small>` : ""}</span></span>`;
  let stats;
  if (view === "units") {
    stats = `<span class="numeric" aria-label="Health">${display(baseValue(record, "base_health"))}</span>
      <span class="numeric" aria-label="Damage">${display(baseValue(record, "attack_damage"))}</span>
      <span class="numeric" aria-label="Gold cost">${display(record.stats.gold_cost.value)}</span>`;
  } else if (audioView) {
    stats = `<span class="numeric">${display(record.duration, " s")}</span>`;
  } else {
    stats = `<span class="numeric">${display(view === "runes" ? record.abilities.length : record.objectives.length)}</span>`;
  }
  const row = `<button type="button" class="record ${view === "units" ? "" : "compact"}" data-id="${escapeText(record.id)}"
    aria-pressed="${active}">${identity}${stats}<span class="chevron" aria-hidden="true">›</span></button>`;
  return audioView ? `<div class="audio-row">${row}${playButton(record)}</div>` : row;
}

function renderList() {
  const matches = visibleRecords();
  const audioView = Object.hasOwn(audioTitles, view);
  const [singular, plural] = sections[view];
  catalog.classList.toggle("with-audio-playback", audioView && Boolean(data.audio_playback || audioFiles.size));
  one("#count").textContent = data[view] ? `${matches.length} ${matches.length === 1 ? singular : plural}` : "";
  sort.hidden = view !== "units";
  if (!matches.some((record) => record.id === selections[view])) selections[view] = matches[0]?.id;
  const headings = view === "units"
    ? '<span>Unit</span><span class="numeric">Health</span><span class="numeric">Damage</span><span class="numeric">Gold</span><span></span>'
    : `<span class="column-label">${singular}</span>
      <span class="numeric">${audioView ? "Duration" : view === "runes" ? "Effects" : "Mission entries"}</span><span></span>`;
  list.innerHTML = matches.length
    ? `<div aria-hidden="true" class="${audioView ? "audio-list-head" : ""}"><div class="list-head ${view === "units" ? "" : "compact"}">
      ${headings}</div></div>${matches.map(listRow).join("")}`
    : `<p class="empty">${data[view] ? "No matches. Try a different search."
      : "Audio catalog unavailable. Extract the APK audio and rebuild the atlas."}</p>`;
  renderDetail(matches.find((record) => record.id === selections[view]));
}

function instructionText(line) {
  const operation = operationNames[line.operation] || line.operation;
  const source = line.source || {};
  const modifier = line.modifier || {};
  const parts = [operation];
  if (source.literal) parts.push(number.format(source.literal.value));
  if (source.register) parts.push(source.register.replace("_", " "));
  if (source.ability_of) parts.push(`using ${source.ability_of} ability ${source.id}`);
  if (source.level_table) parts.push(`by level (${source.level_table.map((item) => number.format(item.value)).join(", ")})`);
  if (modifier.factor) {
    const amount = modifier.factor.value;
    const sign = amount < 0 ? "−" : "+";
    if (modifier.mode === "linear_addition") parts.push(`${sign}${number.format(Math.abs(amount))} per extra level`);
    else parts.push(`${sign}${number.format(Math.abs(amount * 100))}% per extra level${modifier.mode === "compound_multiplier" ? " (compounded)" : ""}`);
  }
  if (modifier.ability_of) parts.push(`modified by ${modifier.ability_of} ability ${modifier.id}`);
  if (line.else_line != null) parts.push(`or jump to line ${line.else_line}`);
  if (line.line != null) parts.push(`to line ${line.line}`);
  return parts.join(" ");
}

function effects(record, title, expanded) {
  if (!record.abilities.length) return "";
  return `<section class="detail-section"><h3>${title}</h3>${record.abilities.map((ability, index) => {
    const initialLine = ability.lines.find((line) => line.source?.literal && line.destination === "result");
    const summary = initialLine ? `<span> · ${escapeText(number.format(initialLine.source.literal.value))}</span>` : "";
    const bounds = ability.bounds.some(Boolean)
      ? `<p>Bounds · ${ability.bounds.map((bound) => bound ? display(bound) : "Unbounded").join(" / ")}</p>` : "";
    return `<details class="effect"${expanded && index === 0 ? " open" : ""}><summary>
      ${escapeText(roleNames[ability.role] || ability.name)}${summary}</summary>
      <ul>${ability.lines.map((line) => `<li>${escapeText(instructionText(line))}
        <span class="offset" title="Decoded asset byte offset">0x${(line.source?.literal?.offset ?? line.offset).toString(16)}</span></li>`).join("")}</ul>
      ${bounds}</details>`;
  }).join("")}</section>`;
}

function statsBlock(title, values) {
  return `<section class="detail-section"><h3>${title}</h3><dl class="stats">
    ${values.map(([label, value, unit]) => `<div><dt>${label}</dt><dd>${display(value, unit)}</dd></div>`).join("")}</dl></section>`;
}

function unitDetails(record) {
  const value = (key) => record.stats[key].value;
  const combat = statsBlock("Base combat stats", [
    ["Health", baseValue(record, "base_health")], ["Damage", baseValue(record, "attack_damage")],
    ["Armor", baseValue(record, "Armor")], ["Attack speed", baseValue(record, "attack_speed")],
    ["Movement speed", baseValue(record, "movement_speed")], ["Vision", baseValue(record, "vision")],
    ["Min. range", baseValue(record, "minimum_attack_range")],
    ["Max. range", baseValue(record, "maximum_attack_range")],
    ["Additional health", baseValue(record, "additional_health")],
  ]);
  const production = statsBlock("Production", [
    ["Gold", value("gold_cost")], ["Gas", value("gas_cost")], ["Population", value("population_cost")],
    ["Base time", value("base_production_seconds"), " s"], ["Units per batch", 1 + value("extra_units_per_batch")],
  ]);
  return combat + '<p class="meta stat-note">Base values can change with level, runes, buffs, and targets.</p>'
    + production + effects(record, "Ability formulas", false);
}

function ruleText(rule) {
  const op = rule.operands;
  if (rule.name === "wait") return `Wait ${number.format(op.seconds.value)} s`;
  if (rule.name === "timer") {
    const seconds = op.duration?.literal?.value;
    return seconds == null ? "Timer instruction" : `Timer · ${number.format(seconds)} s`;
  }
  const amount = (op.delta || op.limit)?.literal?.value;
  const name = rule.name === "resource" ? (["Gold", "Gas"][op.resource_id] || "Resource")
    : rule.name === "max_supply" ? "Supply cap" : "Supply";
  if (amount == null) return `${name} · Formula`;
  const sign = rule.name !== "max_supply" && amount > 0 ? "+" : "";
  return `${name} · ${sign}${number.format(amount)}`;
}

function mapDetails(record) {
  const objectives = record.objectives.length
    ? `<ul class="mission-list">${record.objectives.map((item) => `<li>
      <small class="meta">Mission ${item.id} · Group ${item.group}, line ${item.line}</small>
      <p>${escapeText(item.text || (item.ref ? `Text reference ${item.ref.join("/")}` : "No text"))}</p></li>`).join("")}</ul>`
    : '<p class="meta">No mission entries in this map’s triggers.</p>';
  const rules = record.rules.length ? `<details class="effect"><summary>Timers and resources (${record.rules.length})</summary>
    <ul>${record.rules.map((rule) => `<li>${escapeText(ruleText(rule))}
      <span class="offset">Group ${rule.group}, line ${rule.line}</span></li>`).join("")}</ul></details>` : "";
  return `<section class="detail-section"><h3>Mission entries</h3>${objectives}</section>${rules}`;
}

function playAction(id) {
  return playingRecord?.id === id && !audio.paused ? "Pause" : "Play";
}

function playButton(record) {
  if (!data.audio_playback && !audioFiles.has(record.id)) return "";
  const action = playAction(record.id);
  const name = escapeText(record.name);
  return `<button type="button" class="play-audio" data-play-id="${escapeText(record.id)}"
    data-track-name="${name}" aria-label="${action} ${name}">${action}</button>`;
}

function syncPlayButtons() {
  for (const button of catalog.querySelectorAll("[data-play-id]")) {
    const action = playAction(button.dataset.playId);
    if (button.textContent === action) continue;
    button.textContent = action;
    button.setAttribute("aria-label", `${action} ${button.dataset.trackName}`);
  }
}

function clearAudio() {
  if (!playingRecord) return;
  playingRecord = undefined;
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  if (previewUrl) {
    URL.revokeObjectURL(previewUrl);
    previewUrl = undefined;
  }
  audioPlayer.hidden = true;
  syncPlayButtons();
}

function playAudio(record) {
  if (playingRecord === record && !audio.paused) {
    audio.pause();
    return;
  }
  if (playingRecord !== record || audio.error) {
    clearAudio();
    const file = audioFiles.get(record.id);
    if (data.audio_playback) {
      audio.src = `./apk-audio/${encodeURIComponent(record.id)}`;
    } else if (file) {
      previewUrl = URL.createObjectURL(file);
      audio.src = previewUrl;
    } else {
      return;
    }
    playingRecord = record;
    one("#playing-title").textContent = record.name;
    audioPlayer.hidden = false;
  }
  playbackError.hidden = true;
  audio.play().catch((error) => {
    if (playingRecord === record && error.name !== "AbortError") playbackError.hidden = false;
  });
}

function audioDetails(record) {
  const credits = [
    ["Artist", record.artist], ["Engineer tag", record.engineer],
    ["Album tag", record.album], ["Copyright", record.copyright],
  ].filter(([, value]) => value);
  const context = record.title ? "Title comes from the file’s metadata. The original source is unverified."
    : view === "music" ? "Original track title unverified." : "";
  const uses = record.uses?.length ? `<section class="detail-section"><h3>${{
    "Battle music": "Used in maps", "Map effect": "Used in maps", "Unit voice": "Unit voice references", Announcer: "Language",
  }[record.usage_kind] ?? "In-game references"}</h3>
    <ul class="audio-uses">${record.uses.map((use) => `<li>${escapeText(use)}</li>`).join("")}</ul></section>` : "";
  const gwriter = record.artist === "GWriterStudio";
  const preview = playButton(record) || (audioFiles.size
    ? '<p class="meta">This file is missing from the selected folder.</p>' : "");
  return `${preview}
    <section class="detail-section"><h3>Credits &amp; license</h3>
      ${credits.length ? `<dl class="audio-credits">${credits.map(([label, value]) =>
        `<div><dt>${label}</dt><dd>${escapeText(value)}</dd></div>`).join("")}</dl>`
        : '<p class="meta">No embedded credits found.</p>'}
      <p class="audio-license">${record.license ? `Embedded license ${escapeText(record.license)}.` : "Asset license unverified."}</p>
      ${gwriter ? '<p class="meta"><a href="https://gwriterstudio.artstation.com/projects/q9EAK2">GWriterStudio’s published usage terms</a></p>' : ""}
    </section>${uses}
    <section class="detail-section"><h3>APK source</h3>
      <p class="meta audio-source">${escapeText(record.source)}</p>
      ${record.symbol ? `<p class="meta audio-source">Game reference · ${escapeText(record.symbol)}</p>` : ""}
      ${context ? `<p class="meta">${escapeText(context)}</p>` : ""}
    </section>`;
}

function renderDetail(record) {
  disposeUnitArt();
  if (!record) {
    detail.innerHTML = data[view] ? '<p class="empty">No record selected.</p>' : "";
    return;
  }
  const audioView = Object.hasOwn(audioTitles, view);
  const contents = {
    units: () => (record.art ? unitArtMarkup() : "") + unitDetails(record),
    runes: () => effects(record, "Rune effects", true),
    maps: () => mapDetails(record),
    music: () => audioDetails(record),
    sounds: () => audioDetails(record),
  }[view]();
  const secondary = audioView ? `${number.format(record.duration)} s`
    : view === "maps" ? `${record.id} · ${record.trigger_count} trigger lines` : recordMeta(record);
  detail.innerHTML = `<div class="detail-content"><button type="button" class="back">‹ Back to ${sections[view][1]}</button>
    <div class="detail-heading">${image(record, true)}<div><h2 tabindex="-1">${escapeText(record.name)}</h2>
      <p class="meta">${escapeText(secondary)}</p></div></div>
    ${record.description ? `<p class="description">${escapeText(record.description)}</p>` : ""}${contents}</div>`;
  if (view === "units" && record.art) mountUnitArt(detail.querySelector(".unit-art"), record.art, record.name);
}

function renderMatrix() {
  const head = data.armor_types.map((name) => `<th scope="col">${escapeText(name)}</th>`).join("");
  const rows = data.damage_matrix.map((row, index) => `<tr><th scope="row">${escapeText(data.attack_types[index])}</th>
    ${row.map((cell) => `<td title="Decoded byte offset 0x${cell.offset.toString(16)}">${display(cell.value, "×")}</td>`).join("")}</tr>`);
  one("#matrix").innerHTML = `<h2>Attack vs. armor</h2><p class="meta">Each value is the damage multiplier against that armor class.</p>
    <div class="matrix-wrap"><table><thead><tr><th scope="col">Attack type</th>${head}</tr></thead>
    <tbody>${rows.join("")}</tbody></table></div>`;
}

function switchView(next) {
  if (next !== view) clearAudio();
  if (view === "vfx" && next !== view) closeVfx();
  if (view === "units" && next !== view) disposeUnitArt();
  view = next;
  const audioView = Object.hasOwn(audioTitles, view);
  const vfxView = view === "vfx";
  one("h1").textContent = vfxView ? "Visual effects" : audioTitles[view] ?? "Balance & missions";
  for (const tab of tabs) {
    if (tab.dataset.view === view) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
  }
  catalog.classList.remove("detail-open");
  one("#matrix").hidden = view !== "damage";
  catalog.hidden = view === "damage" || vfxView;
  one("#vfx").hidden = !vfxView;
  one(".audio-folder").hidden = !audioView || !data[view] || data.audio_playback;
  if (vfxView) {
    openVfx();
    return;
  }
  if (view === "damage") {
    detail.replaceChildren();
    return;
  }
  search.value = "";
  search.disabled = !data[view];
  search.placeholder = `Search ${view === "sounds" ? "sound effects" : sections[view][1]}`;
  one("#search-label").textContent = search.placeholder;
  if (!selections[view]) {
    selections[view] = data[view]?.find((record) => record.name === initial[view] || record.id === initial[view])?.id;
  }
  renderList();
}

for (const tab of tabs) tab.addEventListener("click", () => {
  if (!data) return;
  const url = new URL(location.href);
  url.searchParams.set("view", tab.dataset.view);
  if (tab.dataset.view !== "vfx") url.searchParams.delete("effect");
  if (tab.dataset.view !== "units") url.searchParams.delete("unit");
  history.replaceState(null, "", url);
  switchView(tab.dataset.view);
});
search.addEventListener("input", renderList);
sort.addEventListener("change", renderList);
for (const event of ["play", "pause", "ended", "error"]) audio.addEventListener(event, syncPlayButtons);
audio.addEventListener("error", () => { if (playingRecord) playbackError.hidden = false; });
audioFolder.addEventListener("change", () => {
  clearAudio();
  const selectedFiles = new Map([...audioFolder.files].map((file) => [file.name, file]));
  audioFiles = new Map([...data.music, ...data.sounds].flatMap(({ id }) =>
    selectedFiles.has(id) ? [[id, selectedFiles.get(id)]] : []));
  one("#audio-folder-status").textContent = audioFiles.size
    ? `${audioFiles.size} local ${audioFiles.size === 1 ? "file" : "files"} ready to play.`
    : "No matching audio files. Choose the extracted all folder.";
  renderList();
});
catalog.addEventListener("click", (event) => {
  const button = event.target.closest("[data-play-id]");
  if (button) playAudio(data[view].find((record) => record.id === button.dataset.playId));
});
list.addEventListener("click", (event) => {
  const button = event.target.closest("[data-id]");
  if (!button) return;
  list.querySelector('[aria-pressed="true"]')?.setAttribute("aria-pressed", "false");
  button.setAttribute("aria-pressed", "true");
  selections[view] = button.dataset.id;
  if (view === "units") {
    const url = new URL(location.href);
    url.searchParams.set("view", "units");
    url.searchParams.set("unit", selections.units);
    history.replaceState(null, "", url);
  }
  renderDetail(data[view].find((record) => record.id === selections[view]));
  if (mobile.matches) {
    listScroll = window.scrollY;
    catalog.classList.add("detail-open");
    detail.querySelector("h2").focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }
});
detail.addEventListener("click", (event) => {
  if (!event.target.closest(".back")) return;
  disposeUnitArt();
  catalog.classList.remove("detail-open");
  list.querySelector('[aria-pressed="true"]')?.focus({ preventScroll: true });
  window.scrollTo(0, listScroll);
});

fetch("./atlas.json")
  .then((response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  })
  .then((catalogData) => {
    data = catalogData;
    one("#build").textContent = `Game data ${String(data.version).padStart(3, "0")}`;
    renderMatrix();
    const query = new URLSearchParams(location.search);
    const requested = query.get("view");
    const firstView = tabs.some((tab) => tab.dataset.view === requested) ? requested : "units";
    const unit = firstView === "units" && data.units.find((record) => record.id === query.get("unit"));
    if (unit) selections.units = unit.id;
    switchView(firstView);
    if (unit && mobile.matches) catalog.classList.add("detail-open");
    one("#status").hidden = true;
  })
  .catch((error) => {
    one("#status").textContent = "Could not load atlas data. Build the atlas, then open it through localhost.";
    console.error(error);
  });
