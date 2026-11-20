"use strict";

const identityVfxPose = Object.freeze([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);

function vfxPoint(matrix, x, y, z, w = 1) {
  return [
    matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12] * w,
    matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13] * w,
    matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14] * w,
  ];
}

function multiplyVfxPose(a, b) {
  const result = [];
  for (let i = 0; i < 16; i += 4) {
    result.push(...vfxPoint(a, b[i], b[i + 1], b[i + 2], b[i + 3]), b[i + 3]);
  }
  return result;
}

function translateVfxPose(pose, x, y, z) {
  const result = pose.slice();
  result.splice(12, 3, ...vfxPoint(pose, x, y, z));
  return result;
}

function scaleVfxPose(pose, x, y, z) {
  return pose.map((value, index) => index < 12 ? value * [x, y, z][index >> 2] : value);
}

function rotateVfxPose(pose, x, y, z) {
  if (!(x || y || z)) return pose;
  const a = Math.cos(x), b = Math.sin(x);
  const c = Math.cos(y), d = Math.sin(y);
  const e = Math.cos(z), f = Math.sin(z);
  return multiplyVfxPose(pose, [
    c * e, c * f, -d, 0,
    b * d * e - a * f, b * d * f + a * e, b * c, 0,
    a * d * e + b * f, a * d * f - b * e, a * c, 0,
    0, 0, 0, 1,
  ]);
}

function vfxCamera(native, width, height, zoom, battlefield) {
  // Camera::Camera stores the tilt from vertical and places the eye above positive Z.
  const tilt = native?.tilt ?? 42 * Math.PI / 180;
  const sin = Math.sin(tilt), cos = Math.cos(tilt);
  const distance = (native?.distance ?? 2000) / (native?.zoom ?? 1.5);
  const focal = height / (2 * Math.tan((native?.fov ?? Math.PI / 6) / 2));
  const centerX = width / 2, centerY = height * (battlefield ? 0.57 : 0.5);
  return {
    battlefield,
    project(x, y, z) {
      if (!battlefield) return [centerX + x * zoom, centerY + y * zoom, zoom, z];
      const depth = distance - y * sin - z * cos;
      if (depth < (native?.near ?? 100)) return null;
      const scale = zoom * focal / depth;
      return [centerX + x * scale, centerY + (y * cos - z * sin) * scale, scale, depth];
    },
  };
}

function vfxPlane(context, camera, pose, x, y, z, billboard, draw) {
  const world = vfxPoint(pose, x, y, z);
  const origin = camera.project(...world);
  if (!origin) return;
  let right, down;
  if (billboard === 1) {
    const xScale = Math.hypot(pose[0], pose[1], pose[2]) * origin[2];
    const yScale = Math.hypot(pose[4], pose[5], pose[6]) * origin[2];
    const angle = Math.atan2(pose[1], pose[0]);
    const cos = Math.cos(angle), sin = Math.sin(angle);
    right = [cos * xScale, sin * xScale];
    down = [-sin * yScale, cos * yScale];
  } else {
    const p = camera.project(...vfxPoint(pose, x + 1, y, z));
    const q = camera.project(...vfxPoint(pose, x, y + 1, z));
    if (!p || !q) return;
    right = [p[0] - origin[0], p[1] - origin[1]];
    down = [q[0] - origin[0], q[1] - origin[1]];
    if (billboard === 3 && camera.battlefield) {
      down = [0, Math.hypot(pose[4], pose[5], pose[6]) * origin[2]];
    }
  }
  context.save();
  context.transform(...right, ...down, origin[0], origin[1]);
  draw();
  context.restore();
}

function drawVfxTriangle(context, points, uv, texture) {
  const [[ax, ay], [bx, by], [cx, cy]] = points;
  context.save();
  context.beginPath();
  context.moveTo(ax, ay);
  context.lineTo(bx, by);
  context.lineTo(cx, cy);
  context.closePath();
  if (texture) {
    const [[u0, v0], [u1, v1], [u2, v2]] = uv;
    const u = u1 - u0, v = v1 - v0, s = u2 - u0, t = v2 - v0;
    const determinant = u * t - v * s;
    if (Math.abs(determinant) > 0.00001) {
      const a = ((bx - ax) * t - (cx - ax) * v) / determinant;
      const b = ((by - ay) * t - (cy - ay) * v) / determinant;
      const c = ((cx - ax) * u - (bx - ax) * s) / determinant;
      const d = ((cy - ay) * u - (by - ay) * s) / determinant;
      context.clip();
      context.transform(a, b, c, d, ax - a * u0 - c * v0, ay - b * u0 - d * v0);
      context.drawImage(texture, 0, 0);
    }
  } else {
    context.fillStyle = "#aaa5a0";
    context.fill();
  }
  context.restore();
}

function drawVfxModel(context, camera, pose, model, textures) {
  const matrices = [];
  const triangles = [];
  for (const node of model.nodes) {
    const matrix = multiplyVfxPose(matrices[node.parent] ?? pose, node.matrix);
    matrices.push(matrix);
    const texture = textures[node.material] ?? textures[0];
    for (let i = 0; i < node.vertices.length; i += 3) {
      const triangle = node.vertices.slice(i, i + 3);
      const points = triangle.map(([x, y, z]) => camera.project(...vfxPoint(matrix, x, y, z)));
      if (points.some((point) => !point)) continue;
      const uv = texture && triangle.map(([, , , u, v]) => [u * texture.width, v * texture.height]);
      triangles.push({ points, uv, texture, depth: points.reduce((sum, point) => sum + point[3], 0) });
    }
  }
  triangles.sort((a, b) => b.depth - a.depth);
  for (const face of triangles) drawVfxTriangle(context, face.points, face.uv, face.texture);
}
