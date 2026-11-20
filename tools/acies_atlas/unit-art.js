"use strict";

let disposeUnitArt = () => {};

function unitArtMarkup() {
  return `<section class="unit-art detail-section" aria-label="Unit art">
    <div class="unit-art-heading">
      <h3>Unit art</h3>
      <div class="unit-art-facing" hidden>
        <button type="button" class="unit-art-prev" aria-label="Previous facing">‹</button>
        <span class="unit-art-angle"></span>
        <button type="button" class="unit-art-next" aria-label="Next facing">›</button>
      </div>
    </div>
    <div class="unit-art-stage">
      <canvas width="640" height="360" aria-label="Animated unit sprite" hidden></canvas>
      <p class="unit-art-message" role="status">Loading unit art…</p>
    </div>
    <div class="unit-art-options" hidden>
      <label class="unit-art-skin-label">Skin <select class="unit-art-skin"></select></label>
      <label>Motion <select class="unit-art-motion"></select></label>
    </div>
    <div class="unit-art-timeline" hidden>
      <button type="button" class="unit-art-play">Play</button>
      <input type="range" class="unit-art-frame" aria-label="Animation frame" step="1" min="0" value="0">
      <output class="unit-art-frame-number"></output>
    </div>
    <p class="unit-art-source" hidden>
      <span class="unit-art-reference"></span>
      <a class="unit-art-download" download>Sprite sheet</a>
    </p>
  </section>`;
}

function mountUnitArt(root, source, name) {
  const select = (css) => root.querySelector(css);
  const canvas = select("canvas");
  canvas.setAttribute("aria-label", `${name} sprite preview`);
  const paint = canvas.getContext("2d");
  const message = select(".unit-art-message");
  const skinSelect = select(".unit-art-skin");
  const motionSelect = select(".unit-art-motion");
  const facingControls = select(".unit-art-facing");
  const facingText = select(".unit-art-angle");
  const timeline = select(".unit-art-timeline");
  const frameInput = select(".unit-art-frame");
  const frameNumber = select(".unit-art-frame-number");
  const button = select(".unit-art-play");
  const download = select(".unit-art-download");
  const controller = new AbortController();
  const pictures = new Map();
  let skins, image, facing, facingId = 0, frame = 0, raf = 0, request = 0;

  function pause() {
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
    button.textContent = "Play";
  }

  function draw(index) {
    if (!image || !facing || frame === index) return;
    frame = index;
    frameInput.value = String(index);
    frameNumber.value = `${index + 1} / ${facing.frame_count}`;
    const { width, height, columns } = facing;
    const scale = Math.min(canvas.width * 0.76 / width, canvas.height * 0.8 / height, 4);
    const w = width * scale;
    const h = height * scale;
    paint.clearRect(0, 0, canvas.width, canvas.height);
    paint.drawImage(image, (index % columns) * width, Math.floor(index / columns) * height, width, height,
      (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
  }

  function play() {
    if (!facing || !image || facing.frame_count < 2) return;
    const start = performance.now() - frame * facing.frame_seconds * 1000;
    const tick = (now) => {
      const step = Math.floor((now - start) / (facing.frame_seconds * 1000));
      draw(step % facing.frame_count);
      raf = requestAnimationFrame(tick);
    };
    button.textContent = "Pause";
    raf = requestAnimationFrame(tick);
  }

  function loadPicture(url) {
    if (!pictures.has(url)) {
      const art = new Image();
      art.src = url;
      if (pictures.size === 16) pictures.delete(pictures.keys().next().value);
      pictures.set(url, art.decode().then(() => art).catch((error) => {
        pictures.delete(url);
        throw error;
      }));
    }
    return pictures.get(url);
  }

  function motion() {
    return skins[Number(skinSelect.value)].motions[Number(motionSelect.value)];
  }

  async function showFacing() {
    const generation = ++request;
    const current = motion();
    facing = current.facings.find((view) => view.facing === facingId) ?? current.facings[0];
    facingId = facing.facing;
    facingControls.hidden = current.facings.length < 2;
    facingText.textContent = `Facing ${current.facings.indexOf(facing) + 1} / ${current.facings.length}`;
    pause();
    image = null;
    timeline.hidden = true;
    download.parentElement.hidden = true;
    canvas.hidden = true;
    message.hidden = false;
    message.textContent = "Loading sprite…";
    try {
      const picture = await loadPicture(facing.sheet);
      if (generation !== request) return;
      image = picture;
      canvas.hidden = false;
      message.hidden = true;
      frameInput.max = String(facing.frame_count - 1);
      frame = -1;
      draw(0);
      timeline.hidden = facing.frame_count === 1;
      select(".unit-art-reference").textContent = `Animation ${current.source}`;
      download.href = facing.sheet;
      download.parentElement.hidden = false;
    } catch {
      if (generation === request) message.textContent = "This sprite could not be loaded.";
    }
  }

  function showSkin(keepSlot) {
    const motions = skins[Number(skinSelect.value)].motions;
    motionSelect.replaceChildren(...motions.map((entry, i) => {
      const option = new Option(entry.name, i);
      option.dataset.slot = entry.slot;
      return option;
    }));
    motionSelect.selectedIndex = Math.max(0, motions.findIndex((entry) => entry.slot === keepSlot));
    showFacing();
  }

  function turn(delta) {
    if (!skins) return;
    const facings = motion().facings;
    if (facings.length < 2) return;
    const index = facings.findIndex((view) => view.facing === facingId);
    facingId = facings[(index + delta + facings.length) % facings.length].facing;
    showFacing();
  }

  let drag;
  canvas.addEventListener("pointerdown", (event) => {
    if (!event.isPrimary || (event.pointerType === "mouse" && event.button !== 0)) return;
    drag = event.clientX;
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointerup", (event) => {
    if (drag === undefined) return;
    const delta = event.clientX - drag;
    drag = undefined;
    if (Math.abs(delta) > 22) turn(Math.sign(delta));
  });
  canvas.addEventListener("pointercancel", () => { drag = undefined; });
  select(".unit-art-prev").addEventListener("click", () => turn(-1));
  select(".unit-art-next").addEventListener("click", () => turn(1));
  skinSelect.addEventListener("change", () => showSkin(
    Number(motionSelect.selectedOptions[0]?.dataset.slot ?? 0)));
  motionSelect.addEventListener("change", showFacing);
  button.addEventListener("click", () => raf ? pause() : play());
  frameInput.addEventListener("input", () => {
    pause();
    draw(Number(frameInput.value));
  });

  fetch(source, { signal: controller.signal }).then((response) => {
    if (!response.ok) throw new Error("Could not load unit art");
    return response.json();
  }).then((asset) => {
    if (controller.signal.aborted) return;
    skins = asset.skins;
    const names = new Set();
    for (const [index, skin] of skins.entries()) {
      skinSelect.append(new Option(names.has(skin.name) ? `${skin.name} (skin ${skin.index + 1})` : skin.name, index));
      names.add(skin.name);
    }
    select(".unit-art-skin-label").hidden = skins.length === 1;
    select(".unit-art-options").hidden = false;
    showSkin(0);
  }).catch(() => {
    if (!controller.signal.aborted) message.textContent = "Unit art could not be loaded.";
  });

  disposeUnitArt = () => {
    controller.abort();
    request++;
    pause();
    disposeUnitArt = () => {};
  };
}
