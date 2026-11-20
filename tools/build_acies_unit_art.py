#!/usr/bin/env python3
"""Pack original ACIES unit sprites into web-friendly motion and facing sheets."""

from __future__ import annotations

from functools import lru_cache
from math import ceil, sqrt

from PIL import Image, ImageChops

import decode_cdk_animation as cdk
from build_acies_vfx import sprite_frame, write_json

FACING_COUNT = 12
FACING_MASK = ((1 << FACING_COUNT) - 1) << 2


def motion_name(slot):
    index = slot["slot"]
    if index == 0:
        return "Idle"
    if index == 2 and slot["variant"] == 6:
        return "Attack"
    if index == 3 and slot["variant"] == 17:
        return "Move"
    return f"Motion {index}"


def align_offset(bits, size):
    if bits & 1:
        return size / 2
    return size if bits & 2 else 0


def sprite_layers(node, facing=FACING_MASK, delay=0):
    # Object::animationVisibleKey selects one bit from 0x4 through 0x2000.
    mask = node["key_mask"] & FACING_MASK
    if mask:
        facing &= mask
    if not facing:
        return
    delay += max(0, node["latency"])
    sprite = node["substance"]
    if sprite and sprite["kind"] == "sprite" and sprite["bytecode"]["items"]:
        yield facing, delay, sprite
    derivation = node["derivation"]
    if derivation:
        for child in derivation["children"]["items"]:
            yield from sprite_layers(child, facing, delay)


def compose_crop(load_crop, command):
    _, key, x, y, width, height, align, rgba, _, section = command
    texture = load_crop(key)
    if texture is None:
        return None
    if section and section[2] > 0 and section[3] > 0:
        cx, cy, cw, ch = section
        texture = texture.crop((cx, cy, cx + cw, cy + ch))
    w = round(width) if width > 0 else texture.width
    h = round(height) if height > 0 else texture.height
    if not 0 < w <= 4096 or not 0 < h <= 4096:
        return None
    if texture.size != (w, h):
        texture = texture.resize((w, h), Image.Resampling.BILINEAR)
    if rgba != [255] * 4:
        texture = ImageChops.multiply(texture, Image.new("RGBA", texture.size, tuple(rgba)))
    if texture.getbbox() is None:
        return None
    actor = key.split("-", 1)[0] in ("4", "5")
    return texture, round(x - align_offset(align, w)), round(y - align_offset(align >> 2, h)), actor


def frame_at(frames, index, loops, alternate):
    length = len(frames)
    if loops and index >= loops * length:
        return frames[0 if alternate and loops % 2 == 0 else -1]
    cycle, frame = divmod(index, length)
    if alternate and cycle % 2:
        frame = length - frame - 1
    return frames[frame]


def pack_facing(layers, destination, *, body_only=False):
    if body_only:
        # Some motions carry full-size effect sprites alongside the actor.
        layers = [(delay, step, loops, alternate, [[part for part in frame if part[3]] for frame in frames])
                  for delay, step, loops, alternate, frames in layers]
        layers = [layer for layer in layers if any(layer[4])]
    if not layers:
        return None
    # CSSprite uses the stored interval for a single frame (native 0x7e4c1c).
    interval = min(layer[1] for layer in layers)
    length = max(delay + step * len(frames) * (2 if not loops and alternate else 1)
                 for delay, step, loops, alternate, frames in layers)
    count = min(160, max(1, ceil(length / interval - 0.00001)))
    interval = length / count

    drawings = [part for _, _, _, _, frames in layers for frame in frames for part in frame]
    left = min(x for _, x, _, _ in drawings)
    top = min(y for _, _, y, _ in drawings)
    width = max(x + texture.width for texture, x, _, _ in drawings) - left
    height = max(y + texture.height for texture, _, y, _ in drawings) - top
    if max(width, height) > 2048:
        return None
    columns = max(1, min(count, 4096 // width, ceil(sqrt(count * height / width))))
    rows = ceil(count / columns)
    if rows * height > 4096:
        return None
    sheet = Image.new("RGBA", (columns * width, rows * height))
    for i in range(count):
        at = i * interval + 0.000001
        ox, oy = i % columns * width, i // columns * height
        for delay, step, loops, alternate, frames in layers:
            if at < delay:
                continue
            for texture, x, y, _ in frame_at(frames, int((at - delay) / step), loops, alternate):
                sheet.alpha_composite(texture, (ox + x - left, oy + y - top))
    if not sheet.getbbox():
        return None
    sheet.save(destination, "WEBP", lossless=True, method=2)
    return {"sheet": f"unit-art/{destination.name}", "frame_count": count, "columns": columns,
            "width": width, "height": height, "frame_seconds": round(interval, 6)}


def export_motion(node, ref, directory, load_crop):
    layers = list(sprite_layers(node))
    if not layers:
        return []
    # A sheet with no directional descendants (most buildings) needs one view.
    directional = any(mask != FACING_MASK for mask, _, _ in layers)
    prepared = []
    for mask, delay, sprite in layers:
        frames = []
        for row in sprite["bytecode"]["items"]:
            commands = sprite_frame(row, set())
            frames.append([part for cmd in commands if cmd[0] == "image" and (part := compose_crop(load_crop, cmd))])
        if any(frames):
            step = sprite["duration"]
            interval = step if 0.001 <= step <= 15 else 0.1
            prepared.append((mask, (delay, interval, sprite["loop"]["count"], sprite["loop"]["round_trip"], frames)))
    output = []
    for facing in range(FACING_COUNT if directional else 1):
        tracks = [layer for mask, layer in prepared if mask & (4 << facing)]
        if not tracks:
            continue
        path = directory / f"motion-{'-'.join(map(str, ref))}-{facing}.webp"
        if packed := pack_facing(tracks, path) or pack_facing(tracks, path, body_only=True):
            output.append({"facing": facing, **packed})
    return output


def export_unit_art(units, unit_data, asset_root, output, load_atlas, localized_name):
    directory = output / "unit-art"
    directory.mkdir(parents=True, exist_ok=True)
    source = asset_root / "animations.xmf"
    raw, _ = cdk.decode_xmf(source, asset_root)
    reader = cdk.Reader(raw)
    bank, errors = cdk.read_obj_array_partial(reader, 3, cdk.read_animation)
    if errors or reader.remaining:
        raise cdk.ParseError(f"{source.name} did not parse completely")

    @lru_cache(maxsize=2048)
    def load_crop(key):
        group, index, frame = map(int, key.split("-"))
        try:
            image, frames = load_atlas(asset_root, group, index)
            x0, y0, x1, y1 = frames[frame]
        except (OSError, IndexError, ValueError, RuntimeError):
            return None
        if 0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height:
            return image.crop((x0, y0, x1, y1))
        return None

    def get_views(ref):
        branch = bank
        for index in ref:
            if index >= len(branch["items"]):
                return []
            branch = branch["items"][index]
        return export_motion(branch, ref, directory, load_crop)

    records = []
    for unit, (_, row) in zip(units, unit_data, strict=True):
        skins = []
        for index, skin in enumerate(row["skins"]["items"]):
            if skin["slots"]["items"]:
                skins.append((index, localized_name(skin["name"]) or unit["name"], skin["slots"]["items"]))
        if skins:
            records.append((unit, skins))

    # Export each animation once, in native bank order to reuse decoded texture sheets.
    refs = sorted({tuple(slot["index"]) for _, skins in records for _, _, slots in skins for slot in slots})
    views = {ref: get_views(ref) for ref in refs}
    skin_count = 0
    for unit, sources in records:
        skins = []
        for index, name, slots in sources:
            motions = []
            for slot in slots:
                ref = tuple(slot["index"])
                if facings := views[ref]:
                    motions.append({"name": motion_name(slot), "slot": slot["slot"],
                                    "source": "/".join(map(str, ref)), "facings": facings})
            if motions:
                skins.append({"name": name, "index": index, "motions": motions})
        if skins:
            path = directory / f"unit-{unit['id'].replace('/', '-')}.json"
            write_json(path, {"skins": skins})
            unit["art"] = f"unit-art/{path.name}"
            skin_count += len(skins)
    print(f"Unit art: {sum('art' in unit for unit in units)} units, {skin_count} skins, "
          f"{sum(bool(value) for value in views.values())} source motions, {sum(map(len, views.values()))} sheets", flush=True)
