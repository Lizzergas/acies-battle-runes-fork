"use strict";

const vfx = document.querySelector("#vfx");
const effectCanvas = vfx.querySelector("canvas");
const effectContext = effectCanvas.getContext("2d");
const effectTime = vfx.querySelector("#effect-time");
const effectClock = vfx.querySelector("#effect-clock");
const effectZoom = vfx.querySelector("#effect-zoom");
const effectView = vfx.querySelector("#effect-view");
const effectTerrain = vfx.querySelector("#effect-terrain");
const effectSourceArt = vfx.querySelector("#effect-source-art");
const effectBackgroundLabel = vfx.querySelector("#effect-background-label");
const effectBackground = vfx.querySelector("#effect-background");
const effectPlay = vfx.querySelector("#effect-play");
const effectReplay = vfx.querySelector("#effect-replay");
const effectMessage = vfx.querySelector("#effect-message");
const effectStatus = vfx.querySelector("#effect-status");
const effectSearch = vfx.querySelector("#effect-search");
const effectFilter = vfx.querySelector("#effect-filter");
const effectList = vfx.querySelector("#effect-list");
const effectMore = vfx.querySelector("#effect-more");
const effectInfo = vfx.querySelector("#effect-info");
const effectPreviewLabel = vfx.querySelector("#effect-preview-label");
const pictureCache = new Map();
const tintCache = new Map();
const particleTextures = new WeakMap();
const renderWidth = effectCanvas.width;
const renderHeight = effectCanvas.height;

let vfxCatalog, selectedEffect, effectProgram, renderRequest;
let previewRevision = 0, rowLimit = 60, previewTime = 0, autoplayStarted = 0, autoScale = 1;
let previewImages = new Map(), previewMeshes = new Map();
let backgroundTouched = false, representativeTime = 0;
const vfxControls = [effectTime, effectZoom, effectView, effectBackground, effectPlay, effectReplay];

const clamp = (n, lo, hi) => Math.min(Math.max(n, lo), hi);
const vfxNumber = new Intl.NumberFormat("en", { maximumFractionDigits: 2 });
const effectAsset = (id) => `./vfx/sprites/${id}.webp`;

function effectPicture(id) {
  if (!pictureCache.has(id)) {
    const loaded = new Promise((resolve) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => resolve(null);
      img.src = effectAsset(id);
    });
    if (pictureCache.size >= 300) pictureCache.delete(pictureCache.keys().next().value);
    pictureCache.set(id, loaded);
  }
  return pictureCache.get(id);
}

function unmatteGlow(image) {
  if (image.width < 4 || image.height < 4) return image;
  if (particleTextures.has(image)) return particleTextures.get(image);
  const tile = document.createElement("canvas");
  tile.width = image.width;
  tile.height = image.height;
  const context = tile.getContext("2d", { willReadFrequently: true });
  context.drawImage(image, 0, 0);
  const corners = [[0, 0], [tile.width - 1, 0], [0, tile.height - 1], [tile.width - 1, tile.height - 1]];
  const blackMatte = corners.every(([x, y]) => {
    const [r, g, b, a] = context.getImageData(x, y, 1, 1).data;
    return a === 255 && Math.max(r, g, b) <= 20;
  });
  if (!blackMatte) {
    particleTextures.set(image, image);
    return image;
  }
  // Black is neutral for emissive textures, including on a transparent stage.
  const pixels = context.getImageData(0, 0, tile.width, tile.height);
  for (let i = 0; i < pixels.data.length; i += 4) {
    const value = Math.max(pixels.data[i], pixels.data[i + 1], pixels.data[i + 2]);
    if (value) {
      for (let channel = 0; channel < 3; channel++) pixels.data[i + channel] *= 255 / value;
    }
    pixels.data[i + 3] *= value / 255;
  }
  context.putImageData(pixels, 0, 0);
  particleTextures.set(image, tile);
  return tile;
}

function tintedImage(id, image, color) {
  const values = color.slice(0, 3).map((n) => clamp(Math.round(n / 12) * 12, 0, 255));
  if (color.slice(0, 3).every((n) => n >= 249)) return image;
  const key = `${id}:${values.join(",")}`;
  if (!tintCache.has(key)) {
    const tile = document.createElement("canvas");
    tile.width = image.width;
    tile.height = image.height;
    const context = tile.getContext("2d", { willReadFrequently: true });
    context.drawImage(image, 0, 0);
    const pixels = context.getImageData(0, 0, tile.width, tile.height);
    for (let i = 0; i < pixels.data.length; i += 4) {
      for (let channel = 0; channel < 3; channel++) pixels.data[i + channel] *= values[channel] / 255;
    }
    context.putImageData(pixels, 0, 0);
    if (tintCache.size >= 160) tintCache.delete(tintCache.keys().next().value);
    tintCache.set(key, tile);
  }
  return tintCache.get(key);
}

function channelValue(keys, progress, fallback = 0, noise = 0) {
  if (!keys?.length) return fallback;
  const right = keys.findIndex(([t]) => t >= progress);
  const a = keys[right < 0 ? keys.length - 1 : Math.max(0, right - 1)];
  const b = keys[right < 0 ? keys.length - 1 : right];
  const ratio = a[0] === b[0] ? 0 : clamp((progress - a[0]) / (b[0] - a[0]), 0, 1);
  return a[1] + a[2] * noise + ((b[1] - a[1]) + (b[2] - a[2]) * noise) * ratio;
}

function timeProgress(time, seconds, loop) {
  if (!(seconds > 0)) return 0;
  const turns = Math.max(0, time / seconds);
  if (loop?.count && turns >= loop.count) return loop.round_trip && loop.count % 2 === 0 ? 0 : 1;
  return loop?.round_trip && Math.floor(turns) % 2 ? 1 - turns % 1 : turns % 1;
}

function effectPose(transforms, at) {
  let pose = identityVfxPose;
  for (const [start, track] of transforms) {
    const { path, scale, rotation } = track;
    const t = at - start;
    const p = timeProgress(t, path.seconds, path.loop);
    const s = timeProgress(t, scale.seconds, scale.loop);
    const r = timeProgress(t, rotation.seconds, rotation.loop);
    pose = translateVfxPose(pose, channelValue(path.x, p), channelValue(path.y, p), channelValue(path.z, p));
    pose = rotateVfxPose(pose, channelValue(rotation.x, r), channelValue(rotation.y, r), channelValue(rotation.z, r));
    pose = scaleVfxPose(pose, channelValue(scale.x, s, 1), channelValue(scale.y, s, 1), channelValue(scale.z, s, 1));
  }
  return pose;
}

function alignment(bits, size) {
  if (bits & 1) return size / 2;
  return bits & 2 ? size : 0;
}

function blendMode(value) {
  // Native CSGraphics::applyBlendMode uses modes 2, 4 and 5 for these factors.
  return ({ 2: "lighter", 4: "multiply", 5: "screen" })[value] ?? "source-over";
}

function paintImage(context, camera, pose, billboard, command, particle = false) {
  const [id, x, y, width, height, align, color, blend, crop, z = 0] = command;
  const image = previewImages.get(id);
  if (!image || !color[3]) return;
  const texture = blend === 2 || blend === 5 || (particle && blend === 0) ? unmatteGlow(image) : image;
  const glow = texture !== image;
  const source = tintedImage(glow ? `${id}:glow` : id, texture, color);
  const w = width || source.width;
  const h = height || source.height;
  const ox = -alignment(align, w), oy = -alignment(align >> 2, h);
  vfxPlane(context, camera, pose, x, y, z, billboard, () => {
    context.globalAlpha = clamp(color[3] / 255, 0, 1);
    context.globalCompositeOperation = glow ? "lighter" : blendMode(blend);
    if (crop && crop[2] > 0 && crop[3] > 0) context.drawImage(source, ...crop, ox, oy, w, h);
    else context.drawImage(source, ox, oy, w, h);
  });
}

function shapeColor(context, [r, g, b, a]) {
  context.globalAlpha = a / 255;
  context.fillStyle = context.strokeStyle = `rgb(${r},${g},${b})`;
}

function drawSprites(context, camera, pose, layer, age) {
  const rate = layer.seconds > 0 ? timeProgress(age, layer.seconds, layer.loop) : 0;
  const frame = layer.frames[Math.min(layer.frames.length - 1, Math.floor(rate * layer.frames.length))];
  const stack = [];
  let local = pose, billboard = 0;
  for (const [operation, ...args] of frame) {
    switch (operation) {
    case "image":
      paintImage(context, camera, local, billboard, args);
      break;
    case "rect": {
      const [x, y, width, height, color, fill, z = 0] = args;
      vfxPlane(context, camera, local, x, y, z, billboard, () => {
        shapeColor(context, color);
        if (fill) context.fillRect(0, 0, width, height);
        else context.strokeRect(0, 0, width, height);
      });
      break;
    }
    case "line": {
      const [x, y, z, tx, ty, tz, color] = args;
      const a = camera.project(...vfxPoint(local, x, y, z)), b = camera.project(...vfxPoint(local, tx, ty, tz));
      if (!a || !b) break;
      context.save();
      shapeColor(context, color);
      context.beginPath();
      context.moveTo(a[0], a[1]);
      context.lineTo(b[0], b[1]);
      context.stroke();
      context.restore();
      break;
    }
    case "arc": {
      const [x, y, z, width, height, start, end, color, fill] = args;
      vfxPlane(context, camera, local, x, y, z, billboard, () => {
        shapeColor(context, color);
        context.beginPath();
        context.ellipse(width / 2, height / 2, Math.abs(width / 2), Math.abs(height / 2), 0, start, end);
        if (fill) context.fill();
        else context.stroke();
      });
      break;
    }
    case "billboard": billboard = args[0]; break;
    case "translate": local = translateVfxPose(local, ...args); break;
    case "scale": local = scaleVfxPose(local, ...args); break;
    case "rotate": local = rotateVfxPose(local, args[1], args[0], args[2]); break;
    case "push": stack.push([local, billboard]); break;
    case "pop": [local, billboard] = stack.pop() ?? [pose, 0]; break;
    case "reset": [local, billboard] = stack.at(-1) ?? [pose, 0]; break;
    }
  }
}

function particleNoise(index, salt) {
  let bits = Math.imul(index + 137, 0x5bd1e995) ^ Math.imul(salt + 1, 0x27d4eb2d);
  bits = Math.imul(bits ^ (bits >>> 15), 0x85ebca6b);
  return ((bits ^ (bits >>> 13)) >>> 0) / 4294967296;
}

function particleOffset(layer, i) {
  const theta = particleNoise(i, 2) * 2 * Math.PI;
  const sine = Math.sin(theta), cosine = Math.cos(theta);
  const sign = particleNoise(i, 3) * 2 - 1;
  const [width, height = width, depth = 0] = layer.range ?? [layer.radius, layer.radius, 0];
  if (layer.shape === "box" || layer.shape === "rect") {
    return [width * sign, height * (particleNoise(i, 4) * 2 - 1), depth * (particleNoise(i, 5) * 2 - 1)];
  }
  const radius = layer.shell ? 1 : Math.sqrt(particleNoise(i, 4));
  if (layer.shape === "sphere" || layer.shape === "hemisphere") {
    const z = layer.shape === "hemisphere" ? Math.abs(sign) : sign;
    const xy = Math.sqrt(1 - z * z);
    return [width * cosine * xy * radius, height * sine * xy * radius, depth * z * radius];
  }
  return [width * cosine * radius, height * sine * radius, 0];
}

function drawParticles(context, camera, pose, layer, age) {
  const time = age - layer.delay;
  if (time < 0) return;
  const rate = clamp(layer.rate, 0.5, 90);
  const first = Math.max(-Math.ceil(layer.prewarm * rate), Math.floor((time - layer.life - layer.variance) * rate));
  const cap = layer.max > 0 ? Math.min(180, layer.max) : 180;
  const end = Math.floor(Math.min(layer.emission, time) * rate);
  for (let i = Math.max(first, end - cap + 1); i <= end; i++) {
    const noise = particleNoise(i, 1) * 2 - 1;
    const life = Math.max(0.03, layer.life + layer.variance * noise);
    const elapsed = time - i / rate;
    const progress = elapsed / life;
    if (progress >= 1 || progress < 0) continue;
    const index = Math.min(layer.images.length - 1, Math.floor(progress * layer.images.length));
    const id = layer.images[index];
    const image = previewImages.get(id);
    if (!image) continue;
    const theta = particleNoise(i, 2) * 2 * Math.PI;
    const radial = channelValue(layer.radial, progress, 0, noise) * elapsed;
    const [x, y, z] = particleOffset(layer, i);
    const velocity = Array.from({ length: 3 }, (_, k) => channelValue(layer.velocity[k], progress, 0, noise));
    const [vx, vy, vz] = velocity.map((v) => v * elapsed);
    const scale = clamp(channelValue(layer.size, progress, 1, noise), 0.01, 15);
    const color = layer.color.map((values) => 255 * clamp(channelValue(values, progress, 1, noise), 0, 1));
    let instance = translateVfxPose(pose, x + Math.cos(theta) * radial + vx, y + Math.sin(theta) * radial + vy, z + vz);
    let spin = channelValue(layer.spin, progress, 0, noise);
    let stretch = 1;
    let billboard = layer.billboard ?? 1;
    if (billboard === 4) {
      billboard = 1;
      const from = camera.project(...vfxPoint(instance, 0, 0, 0));
      const to = camera.project(...vfxPoint(instance, ...velocity.map((v) => v * 0.01)));
      if (from && to && (from[0] !== to[0] || from[1] !== to[1])) {
        spin += Math.atan2(to[1] - from[1], to[0] - from[0]) - Math.PI / 2;
        stretch = clamp(1 + Math.hypot(...velocity) * (layer.stretch ?? 0.01), 1, 5);
      }
    }
    instance = rotateVfxPose(instance, 0, 0, spin);
    paintImage(context, camera, instance, billboard,
      [id, 0, 0, image.width * scale, image.height * scale * stretch, 5, color, layer.blend], true);
  }
}

function drawTrail(context, camera, pose, layer, age) {
  const progress = clamp(age / (layer.end - layer.start), 0, 1);
  const id = layer.images[Math.min(layer.images.length - 1, Math.floor(progress * layer.images.length))];
  const image = previewImages.get(id);
  if (!image) return;
  const pieces = 9;
  const width = Math.min(260, Math.max(85, image.width));
  const height = clamp(image.height * 0.48, 5, 52);
  const color = layer.color.map((channel) => 255 * clamp(channelValue(channel, progress, 1), 0, 1));
  const texture = layer.blend === 2 || layer.blend === 5 ? unmatteGlow(image) : image;
  const source = tintedImage(texture === image ? id : `${id}:glow`, texture, color);
  const edge = (t, h) => camera.project(...vfxPoint(pose,
    (t - 0.5) * width, 25 * Math.sin(t * Math.PI) + (camera.battlefield ? 0 : h),
    32 * Math.sin(t * Math.PI) + height - h));
  context.save();
  context.globalAlpha = color[3] / 255;
  context.globalCompositeOperation = blendMode(layer.blend);
  for (let i = 0; i < pieces; i++) {
    const a = i / pieces, b = (i + 1) / pieces;
    const corners = [edge(a, 0), edge(b, 0), edge(a, height), edge(b, height)];
    if (corners.some((p) => !p)) continue;
    const u = a * image.width, v = b * image.width;
    drawVfxTriangle(context, [corners[0], corners[1], corners[2]], [[u, 0], [v, 0], [u, image.height]], source);
    drawVfxTriangle(context, [corners[1], corners[3], corners[2]], [[v, 0], [v, image.height], [u, image.height]], source);
  }
  context.restore();
}

function configureEffectStage() {
  const battlefield = effectView.value === "battlefield";
  effectBackgroundLabel.hidden = battlefield;
  effectTerrain.hidden = !battlefield || !vfxCatalog?.battlefield?.image;
  effectCanvas.parentElement.dataset.background = battlefield ? "dark" : effectBackground.value;
  effectPreviewLabel.textContent = battlefield && !effectTerrain.hidden ? "Tutorial 1 terrain capture" : "Web reconstruction";
}

function renderEffect(at) {
  if (!effectProgram) return;
  const battlefield = effectView.value === "battlefield";
  const zoom = effectZoom.value === "fit" ? autoScale : Number(effectZoom.value);
  const camera = vfxCamera(vfxCatalog.battlefield, renderWidth, renderHeight, zoom, battlefield);
  effectContext.clearRect(0, 0, renderWidth, renderHeight);
  for (const layer of effectProgram.layers) {
    if (at < layer.start || at > layer.end) continue;
    const pose = effectPose(layer.transforms, at);
    const age = at - layer.start;
    if (layer.kind === "sprite") drawSprites(effectContext, camera, pose, layer, age);
    else if (layer.kind === "particle") drawParticles(effectContext, camera, pose, layer, age);
    else if (layer.kind === "model") {
      const model = previewMeshes.get(layer.mesh);
      if (model) drawVfxModel(effectContext, camera, pose, model, layer.materials.map((key) => previewImages.get(key)));
    } else drawTrail(effectContext, camera, pose, layer, age);
  }
}

function updatePreviewTime(at) {
  previewTime = at;
  effectTime.value = String(at);
  effectClock.textContent = `${at.toFixed(2)} / ${effectProgram.seconds.toFixed(2)} s`;
  renderEffect(at);
}

function pauseEffect() {
  if (renderRequest) cancelAnimationFrame(renderRequest);
  renderRequest = undefined;
  effectPlay.textContent = "Play";
}

function playEffect() {
  if (!effectProgram) return;
  pauseEffect();
  if (previewTime >= effectProgram.seconds - 0.01) updatePreviewTime(0);
  autoplayStarted = performance.now() - previewTime * 1000;
  effectPlay.textContent = "Pause";
  const frame = (now) => {
    const at = Math.min(effectProgram.seconds, (now - autoplayStarted) / 1000);
    updatePreviewTime(at);
    if (at < effectProgram.seconds && !vfx.hidden) renderRequest = requestAnimationFrame(frame);
    else {
      if (!vfx.hidden) updatePreviewTime(representativeTime);
      pauseEffect();
    }
  };
  renderRequest = requestAnimationFrame(frame);
}

function previewScale(program) {
  let extent = 1;
  for (const layer of program.layers) {
    let size = 0;
    if (layer.kind === "sprite") {
      for (const frame of layer.frames) for (const command of frame) {
        if (command[0] === "image") {
          const [, id, x, y, w, h, , , , , z = 0] = command;
          const image = previewImages.get(id);
          if (image) size = Math.max(size, Math.abs(x) + (w || image.width) / 2, Math.abs(y) + (h || image.height) / 2, Math.abs(z));
        } else if (command[0] === "rect") {
          const [, x, y, w, h] = command;
          size = Math.max(size, Math.abs(x) + Math.abs(w) / 2, Math.abs(y) + Math.abs(h) / 2);
        }
      }
    } else if (layer.kind === "model") {
      for (const node of previewMeshes.get(layer.mesh)?.nodes ?? []) {
        for (const [x, y, z] of node.vertices) {
          size = Math.max(size, ...vfxPoint(node.matrix, x, y, z).map(Math.abs));
        }
      }
    } else {
      for (const id of layer.images) {
        const image = previewImages.get(id);
        if (image) size = Math.max(size, (Math.max(image.width, image.height) / 2 + (layer.radius ?? 55)) * 1.4);
      }
    }
    for (const at of [layer.start, (layer.start + layer.end) / 2, layer.end]) {
      const pose = effectPose(layer.transforms, at);
      const stretch = Math.max(Math.hypot(...pose.slice(0, 3)), Math.hypot(...pose.slice(4, 7)), Math.hypot(...pose.slice(8, 11)));
      extent = Math.max(extent, Math.max(...pose.slice(12, 15).map(Math.abs)) + size * stretch);
    }
  }
  return clamp((effectView.value === "battlefield" ? 275 : 185) / extent, 0.025, 30);
}

function firstVisibleTime(program) {
  const sample = document.createElement("canvas");
  sample.width = 72;
  sample.height = 40;
  const context = sample.getContext("2d", { willReadFrequently: true });
  const times = new Set(Array.from({ length: 12 }, (_, i) => program.seconds * i / 12));
  // Include starts and short visible windows even when the overall effect is long.
  for (const layer of program.layers.slice(0, 32)) {
    const from = layer.start + (layer.delay ?? 0);
    const length = Math.min(layer.end - from, layer.life ?? layer.seconds ?? 0.2);
    times.add(from);
    times.add(from + Math.max(0, length) * 0.5);
    times.add(from + Math.max(0, length) * 0.35);
    times.add(from + Math.max(0, length) * 0.7);
  }
  let best = { time: 0, score: 0, luma: 0 };
  for (const time of times) {
    if (time > program.seconds) continue;
    renderEffect(time);
    context.clearRect(0, 0, sample.width, sample.height);
    context.drawImage(effectCanvas, 0, 0, sample.width, sample.height);
    const pixels = context.getImageData(0, 0, sample.width, sample.height).data;
    let coverage = 0, luminance = 0;
    for (let i = 3; i < pixels.length; i += 4) {
      const alpha = pixels[i];
      coverage += alpha;
      luminance += (pixels[i - 3] * 0.213 + pixels[i - 2] * 0.715 + pixels[i - 1] * 0.072) * alpha;
    }
    const score = coverage * 0.4 + luminance / 255;
    if (score > best.score) best = { time, score, luma: luminance / coverage };
  }
  return best;
}

function unavailableEffect(record, text) {
  const sources = record?.layers ?? {};
  if (!text) {
    if (!Object.keys(sources).length) text = "Timing record. No drawable layers.";
    else if (record.limits.includes("Sprite command 29")) text = "This entry needs the game’s interface drawing code.";
    else if (record.limits.includes("Sprite command 31")) text = "This lens effect needs the game’s framebuffer.";
    else text = "No browser-renderable frames are available.";
  }
  effectMessage.hidden = false;
  effectMessage.textContent = text;
  if (record?.icon) {
    effectSourceArt.src = record.icon;
    effectSourceArt.hidden = false;
    effectMessage.classList.add("with-source");
  }
}

function applyEffectView() {
  configureEffectStage();
  if (!effectProgram) return;
  autoScale = previewScale(effectProgram);
  renderEffect(previewTime);
}

async function showEffect(record) {
  const revision = ++previewRevision;
  selectedEffect = record?.id;
  pauseEffect();
  effectProgram = null;
  effectCanvas.hidden = true;
  effectSourceArt.hidden = true;
  effectTerrain.hidden = true;
  effectMessage.classList.remove("with-source");
  effectPreviewLabel.hidden = true;
  effectMessage.hidden = false;
  effectMessage.textContent = "Loading animation…";
  for (const input of vfxControls) input.disabled = true;
  effectTime.value = "0";
  effectClock.textContent = "";
  vfx.querySelector("#effect-title").textContent = record?.name ?? "No effect selected";
  vfx.querySelector("#effect-id").textContent = record ? `Animation ${record.id}` : "";
  effectInfo.replaceChildren();
  if (!record) {
    effectMessage.textContent = "Select an effect to preview it.";
    return;
  }
  const uses = record.tutorials ?? [];
  const usedIn = uses.slice(0, 6).map((use) => `${use.title} · group ${use.group}, line ${use.line}`);
  if (uses.length > usedIn.length) usedIn.push(`${uses.length - usedIn.length} more triggers`);
  const details = [
    ["Layers", Object.entries(record.layers).map(([kind, count]) => `${count} ${kind}`).join(" · ") || "No visible layer"],
    ["Source", `animations.xmf · 0x${record.offset.toString(16)}`],
    ["Used in", usedIn.join("\n") || record.evidence],
    ["Preview limits", record.limits.join(", ")],
  ].filter(([, value]) => value);
  for (const [label, value] of details) {
    const term = document.createElement("dt");
    const text = document.createElement("dd");
    term.textContent = label;
    text.textContent = value;
    effectInfo.append(term, text);
  }
  const url = new URL(location.href);
  url.searchParams.set("view", "vfx");
  url.searchParams.set("effect", record.id);
  history.replaceState(null, "", url);
  if (!record.preview) {
    unavailableEffect(record);
    return;
  }
  try {
    const response = await fetch(record.preview);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const program = await response.json();
    if (revision !== previewRevision) return;
    const [pictures, models] = await Promise.all([
      Promise.all(program.images.map(async (id) => [id, await effectPicture(id)])),
      Promise.all((program.meshes ?? []).map(async (id) => {
        const response = await fetch(`vfx/meshes/${id}.json`);
        if (!response.ok) throw new Error(`Mesh ${id}: HTTP ${response.status}`);
        return [id, await response.json()];
      })),
    ]);
    if (revision !== previewRevision) return;
    previewImages = new Map(pictures);
    previewMeshes = new Map(models);
    effectProgram = program;
    const requestedView = new URL(location.href).searchParams.get("camera");
    effectView.value = requestedView === "battlefield" || requestedView === "isolated"
      ? requestedView : record.world ? "battlefield" : "isolated";
    effectZoom.value = record.world && record.kind !== "model" ? "1" : "fit";
    if (!backgroundTouched) effectBackground.value = "dark";
    configureEffectStage();
    autoScale = previewScale(program);
    let frame = firstVisibleTime(program);
    if (!frame.score && effectZoom.value !== "fit") {
      effectZoom.value = "fit";
      frame = firstVisibleTime(program);
    }
    if (!frame.score && effectView.value === "battlefield") {
      effectView.value = "isolated";
      autoScale = previewScale(program);
      configureEffectStage();
      frame = firstVisibleTime(program);
    }
    if (!frame.score) {
      effectProgram = null;
      effectTerrain.hidden = true;
      unavailableEffect(record, record.icon ? "Source frame. Playback requires additional game rendering." : undefined);
      return;
    }
    if (!backgroundTouched && effectView.value === "isolated" && frame.luma < 40) {
      effectBackground.value = "light";
      configureEffectStage();
    }
    representativeTime = frame.time;
    effectTime.max = String(program.seconds);
    effectCanvas.hidden = false;
    effectPreviewLabel.hidden = false;
    effectMessage.hidden = true;
    for (const input of vfxControls) input.disabled = false;
    updatePreviewTime(representativeTime);
  } catch (error) {
    if (revision !== previewRevision) return;
    effectProgram = null;
    effectTerrain.hidden = true;
    unavailableEffect(record, "Could not load this preview. Refresh the atlas to try again.");
    console.error(error);
  }
}

function vfxRows() {
  const input = effectSearch.value.trim().toLowerCase();
  const filter = effectFilter.value;
  return vfxCatalog.records.filter((record) => {
    const uses = record.tutorials ?? [];
    if (filter === "tutorial" && !uses.length) return false;
    if (filter === "playable" && !record.preview) return false;
    if (filter === "unavailable" && record.preview) return false;
    if (filter.startsWith("tutorial-") && !uses.some((use) => filter === `tutorial-${use.tutorial}`)) return false;
    return [record.name, record.id, record.kind, record.evidence, ...Object.keys(record.layers), ...uses.map((use) => use.title)]
      .some((value) => value.toLowerCase().includes(input));
  });
}

function renderEffectsList() {
  if (!vfxCatalog) return;
  const results = vfxRows();
  const playable = results.filter((record) => record.preview).length;
  effectStatus.textContent = `${vfxNumber.format(results.length)} entries · ${vfxNumber.format(playable)} previews`;
  if (vfxCatalog.remaining || vfxCatalog.errors.length) effectStatus.textContent += " · Partial catalog";
  effectList.replaceChildren();
  for (const record of results.slice(0, rowLimit)) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "vfx-row";
    row.dataset.effectId = record.id;
    row.setAttribute("aria-pressed", String(record.id === selectedEffect));
    const title = document.createElement("span");
    title.textContent = record.name;
    const type = document.createElement("span");
    type.textContent = record.kind;
    type.className = "vfx-kind";
    const icon = document.createElement(record.icon ? "img" : "span");
    icon.className = "vfx-thumb";
    if (record.icon) {
      icon.src = record.icon;
      icon.alt = "";
      icon.loading = "lazy";
      icon.width = icon.height = 36;
    }
    row.append(icon, title, type);
    effectList.append(row);
  }
  if (!results.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No effects match this search.";
    effectList.append(empty);
  }
  effectMore.hidden = results.length <= rowLimit;
}

function mountVfxCaptures(captures) {
  const gallery = vfx.querySelector("#vfx-captures");
  gallery.hidden = captures.length === 0;
  vfx.querySelector("#effect-capture-link").hidden = gallery.hidden;
  const grid = gallery.querySelector(".vfx-capture-grid");
  grid.replaceChildren();
  for (const capture of captures) {
    const figure = document.createElement("figure");
    const caption = document.createElement("figcaption");
    const title = document.createElement("strong");
    const description = document.createElement("p");
    title.textContent = capture.title;
    description.textContent = capture.description;
    caption.append(title, description);
    if (capture.image) {
      const link = document.createElement("a");
      link.href = capture.image;
      const image = document.createElement("img");
      image.src = capture.image;
      image.alt = capture.title;
      image.loading = "lazy";
      link.append(image);
      figure.append(link);
    } else {
      const video = document.createElement("video");
      video.controls = true;
      video.playsInline = true;
      video.preload = "metadata";
      video.src = capture.video;
      if (capture.poster) video.poster = capture.poster;
      figure.className = "vfx-capture-video";
      figure.append(video);
    }
    figure.append(caption);
    grid.append(figure);
  }
}

function mountVfxPortraits(portraits) {
  const section = vfx.querySelector("#vfx-portraits");
  section.hidden = !portraits.length;
  const grid = section.querySelector(".vfx-portrait-grid");
  for (const portrait of portraits) {
    const figure = document.createElement("figure");
    const link = document.createElement("a");
    const image = document.createElement("img");
    const caption = document.createElement("figcaption");
    const title = document.createElement("strong");
    const usage = document.createElement("p");
    link.href = image.src = portrait.image;
    image.alt = portrait.title;
    image.loading = "lazy";
    title.textContent = portrait.title;
    usage.textContent = portrait.tutorials.join(" · ");
    link.append(image);
    caption.append(title, usage);
    figure.append(link, caption);
    grid.append(figure);
  }
}

async function openVfx() {
  if (vfxCatalog) {
    showEffect(vfxCatalog.records.find((record) => record.id === selectedEffect) ?? vfxCatalog.records[0]);
    return;
  }
  effectStatus.textContent = "Loading effects…";
  try {
    const response = await fetch("./vfx/catalog.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    vfxCatalog = await response.json();
    if (vfxCatalog.battlefield?.image) effectTerrain.src = vfxCatalog.battlefield.image;
    const requested = new URLSearchParams(location.search).get("effect");
    const record = vfxCatalog.records.find((item) => item.id === requested) ?? vfxCatalog.records[0];
    selectedEffect = record?.id;
    const lessonOptions = document.createElement("optgroup");
    lessonOptions.label = "Campaign tutorials";
    (vfxCatalog.tutorials ?? []).forEach((title, index) => lessonOptions.append(new Option(title, `tutorial-${index}`)));
    effectFilter.append(lessonOptions);
    mountVfxCaptures(vfxCatalog.captures);
    mountVfxPortraits(vfxCatalog.portraits ?? []);
    renderEffectsList();
    if (!vfx.hidden) {
      await showEffect(record);
      if (location.hash === "#vfx-captures" || location.hash === "#vfx-portraits") {
        document.getElementById(location.hash.slice(1)).scrollIntoView();
      }
    }
  } catch (error) {
    effectStatus.textContent = "Effect catalog unavailable. Rebuild the atlas with the extracted APK.";
    console.error(error);
  }
}

function closeVfx() {
  pauseEffect();
  vfx.querySelector("video")?.pause();
}

for (const field of [effectSearch, effectFilter]) {
  field.addEventListener(field === effectSearch ? "input" : "change", () => {
    rowLimit = 60;
    renderEffectsList();
  });
}
effectMore.addEventListener("click", () => {
  const previous = rowLimit;
  rowLimit += 60;
  renderEffectsList();
  effectList.querySelectorAll("button")[previous]?.focus();
});
effectList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-effect-id]");
  if (!button) return;
  effectList.querySelector('[aria-pressed="true"]')?.setAttribute("aria-pressed", "false");
  button.setAttribute("aria-pressed", "true");
  const url = new URL(location.href);
  url.searchParams.delete("camera");
  history.replaceState(null, "", url);
  showEffect(vfxCatalog.records.find((record) => record.id === button.dataset.effectId));
  if (matchMedia("(max-width: 670px)").matches) vfx.querySelector("#effect-title").focus();
});
effectPlay.addEventListener("click", () => renderRequest ? pauseEffect() : playEffect());
effectReplay.addEventListener("click", () => {
  if (effectProgram) {
    updatePreviewTime(0);
    playEffect();
  }
});
effectTime.addEventListener("input", () => {
  pauseEffect();
  updatePreviewTime(Number(effectTime.value));
});
effectZoom.addEventListener("input", () => renderEffect(previewTime));
effectView.addEventListener("change", () => {
  const url = new URL(location.href);
  url.searchParams.set("camera", effectView.value);
  history.replaceState(null, "", url);
  applyEffectView();
});
effectBackground.addEventListener("change", () => {
  backgroundTouched = true;
  configureEffectStage();
});
