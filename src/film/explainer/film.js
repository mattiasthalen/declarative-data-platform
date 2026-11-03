// The explainer's composition. Every frame is a pure function of t (seconds): the renderer seeks
// each frame with window.__seek(t) and screenshots it, so a render is the same every time.
// window.FILM holds what film/render.py read from the declarations and the timeline.

const F = window.FILM;
const $ = (id) => document.getElementById(id);
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const prog = (t, a, b) => clamp((t - a) / (b - a));
const outCubic = (x) => 1 - Math.pow(1 - x, 3);
const inCubic = (x) => x * x * x;
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const NS = 'http://www.w3.org/2000/svg';

const COLOUR = { raw: 'var(--raw)', contract: 'var(--contract)', anchor: 'var(--anchor)', serve: 'var(--serve)', text: 'var(--text)' };

// The words on screen for each layer chapter: what it does, and the shapes either side of its declaration.
const LAYERS = {
  ingest: { n: 1, title: 'Ingest', sub: 'Lands every load in the lake, as it came.', before: ['feed', 'THE SOURCE'], after: ['raw', 'RAW, IN THE LAKE'], colour: 'raw', zoom: ['resource declared', 'resources declared'] },
  conform: { n: 2, title: 'Conform', sub: 'Types every row by its data contract.', before: ['raw', 'RAW'], after: ['grid', 'TYPED AND STAGED'], colour: 'contract', zoom: ['contract declared', 'contracts declared'] },
  integrate: { n: 3, title: 'Integrate', sub: 'Keeps every change, true to Anchor Modeling.', before: ['grid', 'STAGED'], after: ['anchor', 'THE ANCHOR MODEL'], colour: 'anchor', zoom: ['anchor in the model', 'anchors in the model'] },
  serve: { n: 4, title: 'Serve', sub: 'Answers questions through one bridge.', before: ['anchor', 'THE ANCHOR MODEL'], after: ['star', 'TODAY, A STAR SCHEMA'], colour: 'serve', zoom: ['dimension and the bridge, today', 'dimensions and the bridge, today'] },
};

const chapterOf = Object.fromEntries(F.chapters.map((c) => [c.name, c]));
const span = {};
for (const b of F.beats) {
  const s = (span[b.chapter] ||= { start: b.start, end: b.end, beats: {} });
  s.end = b.end;
  s.beats[b.beat] = b;
}

function st(el, { op = 1, x = 0, y = 0, s = 1 } = {}) {
  el.style.opacity = op;
  el.style.visibility = op <= 0.002 ? 'hidden' : 'visible';
  el.style.transform = `translate(${x.toFixed(2)}px, ${y.toFixed(2)}px) scale(${s})`;
}
// rise and fade in at t0, fade and lift out at t1
function envelope(t, t0, t1, rise = 0.6, fall = 0.45) {
  const a = outCubic(prog(t, t0, t0 + rise));
  const b = inCubic(prog(t, t1 - fall, t1));
  return { op: a * (1 - b), y: (1 - a) * 22 - b * 14 };
}
function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}

// ------------------------------------------------------------------ shapes
// The hero's four stages (film/stages.py), drawn at the side of a card. Coordinates are the
// hero's: tile corners of 22px squares; each shape is fitted into a 340px box.
function fit(points) {
  const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
  const x0 = Math.min(...xs), y0 = Math.min(...ys), x1 = Math.max(...xs) + 22, y1 = Math.max(...ys) + 22;
  const scale = 250 / Math.max(x1 - x0, y1 - y0);
  return (p) => [170 + (p[0] - (x0 + x1) / 2) * scale, 170 + (p[1] - (y0 + y1) / 2) * scale, scale];
}
function shape(kind, colour) {
  const g = document.createElementNS(NS, 'g');
  const S = F.stages;
  const parts = [];
  const add = (svg) => parts.push(svg);
  if (kind === 'feed') {
    for (let r = 0; r < 3; r++) for (let k = 0; k < 7; k++) add(`<circle class="dot" data-r="${r}" data-k="${k}" r="5" cy="${110 + r * 60}" fill="${COLOUR.raw}"/>`);
    add(`<rect x="10" y="80" width="40" height="180" rx="8" fill="var(--surface)" stroke="${COLOUR.raw}" stroke-width="2"/>`);
  } else {
    const layout = { raw: S.raw, grid: S.grid, anchor: S.anchor, star: S.star }[kind];
    const at = fit(layout);
    const centre = (i) => { const [x, y, s] = at(layout[i]); return [x + 11 * s, y + 11 * s, s]; };
    const lit = `fill="var(--claimed)" stroke="${COLOUR[colour]}" stroke-width="2.4"`;
    const frame = `fill="var(--surface)" stroke="${COLOUR[colour]}" stroke-opacity="0.9" stroke-width="2"`;
    if (kind === 'anchor') {
      const anchorOf = (i) => (layout[i][0] < layout[S.tie[0]][0] ? S.anchors[0] : S.anchors[1]);
      for (const i of S.attributes) { const [x1, y1] = centre(i), [x2, y2] = centre(anchorOf(i)); add(`<line class="ln" data-i="${i}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${COLOUR[colour]}" stroke-opacity="0.55" stroke-width="2"/>`); }
      for (const a of S.anchors) { const [x1, y1] = centre(a), [x2, y2] = centre(S.tie[0]); add(`<line class="ln" data-i="${S.tie[0]}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${COLOUR[colour]}" stroke-opacity="0.55" stroke-width="2"/>`); }
    }
    if (kind === 'star') {
      const [cx, cy] = centre(S.bridge);
      layout.forEach((_, i) => { if (i !== S.bridge) { const [x, y] = centre(i); add(`<line class="ln" data-i="${i}" x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="${COLOUR[colour]}" stroke-opacity="0.55" stroke-width="2"/>`); } });
    }
    layout.forEach((p, i) => {
      const [x, y, s] = at(p);
      const w = 22 * s, [cx, cy] = centre(i);
      let body;
      if (kind === 'anchor' && S.attributes.includes(i)) body = `<circle cx="${cx}" cy="${cy}" r="${9 * s}" ${frame}/><circle cx="${cx}" cy="${cy}" r="${5.5 * s}" fill="none" stroke="${COLOUR[colour]}" stroke-width="1.6"/>`;
      else if (kind === 'anchor' && S.tie.includes(i)) body = `<polygon points="${cx},${cy - 12 * s} ${cx + 12 * s},${cy} ${cx},${cy + 12 * s} ${cx - 12 * s},${cy}" ${frame}/>`;
      else if (kind === 'star' && i === S.bridge) body = `<polygon points="${cx},${cy - 13 * s} ${cx + 13 * s},${cy} ${cx},${cy + 13 * s} ${cx - 13 * s},${cy}" ${lit}/><circle cx="${cx}" cy="${cy}" r="${3.5 * s}" fill="${COLOUR[colour]}"/>`;
      else if (kind === 'anchor' && S.anchors.includes(i)) body = `<rect x="${x}" y="${y}" width="${w}" height="${w}" rx="${4 * s}" ${lit}/><circle cx="${cx}" cy="${cy}" r="${3.5 * s}" fill="${COLOUR[colour]}"/>`;
      else body = `<rect x="${x}" y="${y}" width="${w}" height="${w}" rx="${4 * s}" ${frame}/>`;
      add(`<g class="tile" data-i="${i}" style="transform-origin:${cx}px ${cy}px">${body}</g>`);
    });
  }
  g.innerHTML = parts.join('');
  return g;
}
function side(cls, [kind, label], colour) {
  const box = el('div', `layer side ${cls}`);
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 340 340');
  svg.appendChild(shape(kind, colour));
  box.appendChild(svg);
  box.appendChild(el('div', 'label', esc(label)));
  box.kind = kind;
  return box;
}
// the shape's tiles appear one by one from t0 to t1; before t0 the shape is drawn whole when `whole`
function buildShape(box, t, t0, t1, whole) {
  const tiles = box.querySelectorAll('.tile');
  const order = [...tiles].map((tile) => +tile.dataset.i);
  tiles.forEach((tile, k) => {
    const a = whole ? 1 : outCubic(prog(t, t0 + (k / tiles.length) * (t1 - t0), t0 + (k / tiles.length) * (t1 - t0) + 0.5));
    tile.style.opacity = a;
    tile.style.transform = `scale(${0.6 + 0.4 * a})`;
  });
  box.querySelectorAll('.ln').forEach((line) => {
    const k = order.indexOf(+line.dataset.i);
    line.style.opacity = whole ? 1 : outCubic(prog(t, t0 + ((k + 0.5) / tiles.length) * (t1 - t0), t0 + ((k + 0.5) / tiles.length) * (t1 - t0) + 0.5));
  });
  box.querySelectorAll('.dot').forEach((dot) => {
    const r = +dot.dataset.r, k = +dot.dataset.k;
    const x = 60 + ((t * 70 + k * 40 + r * 23) % 280);
    dot.setAttribute('cx', x.toFixed(2));
    dot.setAttribute('opacity', (Math.sin(Math.PI * ((x - 60) / 280)) * 0.9).toFixed(3));
  });
}

// ------------------------------------------------------------------ cards
function yaml(line) {
  if (/^\s*#/.test(line)) return `<span class="c">${esc(line)}</span>`;
  const m = line.match(/^(\s*)(- )?([A-Za-z_][\w$]*)(:)(.*)$/);
  if (!m) return `<span class="s">${esc(line)}</span>`;
  const [, ws, dash, key, colon, rest] = m;
  return `${ws}${dash ? `<span class="p">${dash}</span>` : ''}<span class="k">${esc(key)}</span><span class="p">${colon}</span><span class="s">${esc(rest)}</span>`;
}
function card(shown, colour) {
  const box = el('div', 'layer card');
  const from = shown.start > 1 ? `<span class="from">from line ${shown.start}</span>` : '';
  box.innerHTML = `<div class="path"><span class="dot" style="background:${COLOUR[colour]}"></span>${esc(shown.path)}${from}</div>` +
    `<pre>${shown.lines.map((line, i) => `<span class="ln"><span class="no">${shown.elided && i === shown.lines.length - 1 ? '' : shown.start + i}</span>${yaml(line)}</span>`).join('')}</pre>`;
  return box;
}
// a card sits centred on the line through the middle of the side shapes (film.css .side)
function centreCard(box) {
  const scene = box.parentElement;
  scene.style.display = 'block';
  box.style.top = `${Math.round(570 - box.offsetHeight / 2)}px`;
  scene.style.display = '';
}
function typeCard(box, t, t0) {
  box.querySelectorAll('pre .ln').forEach((line, i) => {
    const a = outCubic(prog(t, t0 + i * 0.07, t0 + i * 0.07 + 0.35));
    line.style.opacity = a;
    line.style.transform = `translateX(${((1 - a) * 12).toFixed(2)}px)`;
  });
}

// ------------------------------------------------------------------ zoom-outs
const ZOOM_W = 1680, ZOOM_H = 560;
function tileShape(tile, box, colour) {
  const { x, y, w } = box, cx = x + w / 2, cy = y + 34 + w / 2;
  const stroke = COLOUR[colour];
  const claimed = tile.featured || tile.kind === 'bridge' || tile.kind === 'build';
  const fill = claimed ? 'var(--claimed)' : 'var(--surface)';
  const r = Math.max(3, w * 0.16);
  let body;
  if (tile.kind === 'next') body = `<rect x="${x}" y="${y + 34}" width="${w}" height="${w}" rx="${r}" fill="none" stroke="var(--label)" stroke-dasharray="7 6" stroke-width="2"/>`;
  else if (tile.kind === 'bridge') body = `<polygon points="${cx},${cy - w * 0.56} ${cx + w * 0.56},${cy} ${cx},${cy + w * 0.56} ${cx - w * 0.56},${cy}" fill="${fill}" stroke="${stroke}" stroke-width="2.4"/>`;
  else body = `<rect x="${x}" y="${y + 34}" width="${w}" height="${w}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${claimed ? 2.4 : 2}"/>`;
  if (claimed) body += `<circle cx="${cx}" cy="${cy}" r="${Math.max(3, w * 0.07)}" fill="${stroke}"/>`;
  const [owner, own] = tile.name.includes('__') ? tile.name.split('__') : ['', tile.kind === 'next' ? 'next shape' : tile.name];
  const below = tile.kind === 'anchor' && tile.attributes ? w * 0.48 : 0;
  const label = w >= 56 ? `<text class="tilename" x="${cx}" y="${y + 34 + w + 26 + below}" text-anchor="middle">${esc(own)}` +
    (owner ? `<tspan class="of" x="${cx}" dy="19">${esc(owner)}</tspan>` : '') + '</text>' : '';
  if (tile.kind === 'anchor') {
    // the anchor's attributes, as the hero draws them: small circles around it
    for (let k = 0; k < tile.attributes; k++) {
      const a = -Math.PI / 2 + (k / tile.attributes) * Math.PI * 2, rr = w * 0.86;
      const ax = cx + Math.cos(a) * rr, ay = cy + Math.sin(a) * rr;
      body = `<line x1="${cx + Math.cos(a) * w * 0.5}" y1="${cy + Math.sin(a) * w * 0.5}" x2="${ax - Math.cos(a) * w * 0.12}" y2="${ay - Math.sin(a) * w * 0.12}" stroke="${stroke}" stroke-opacity="0.55" stroke-width="2"/>` +
        `<circle cx="${ax}" cy="${ay}" r="${w * 0.12}" fill="var(--surface)" stroke="${stroke}" stroke-width="2"/>` + body;
    }
  }
  return `<g class="ztile" style="transform-origin:${cx}px ${cy}px">${body}${label}</g>`;
}
function zoom(name, colour, label) {
  const box = el('div', 'layer zoom');
  const tiles = [...chapterOf[name].zoom_out.tiles];
  if (name === 'serve') tiles.push({ kind: 'next', name: 'next shape' });
  const placed = F.zoom[name];
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${ZOOM_W} 604`);
  svg.innerHTML = tiles.map((tile, i) => tileShape(tile, placed[i], colour)).join('');
  box.appendChild(svg);
  const count = chapterOf[name].zoom_out.tiles.length;
  box.appendChild(el('div', 'label', `The whole model · ${count} ${esc(count === 1 ? label[0] : label[1])}`));
  return box;
}
function growZoom(box, t, t0) {
  const tiles = box.querySelectorAll('.ztile');
  const step = Math.min(0.12, 2.4 / tiles.length);
  tiles.forEach((tile, i) => {
    const a = outCubic(prog(t, t0 + 0.5 + i * step, t0 + 0.9 + i * step));
    tile.style.opacity = a;
    tile.style.transform = `scale(${0.7 + 0.3 * a})`;
  });
}

// ------------------------------------------------------------------ scenes
const scenes = [];
function scene(id) { const s = el('div', 'scene'); s.id = id; $('scenes').appendChild(s); return s; }
function header(kicker, title, sub) {
  return el('div', 'layer header', `<div class="kicker">${esc(kicker)}</div><div class="title">${esc(title)}</div>${sub ? `<div class="sub">${esc(sub)}</div>` : ''}`);
}

// hook: a scatter of hand-made tiles that snaps into one grid with one claimed tile
{
  const s = scene('hook'), { start, end } = span.hook;
  const first = el('div', 'layer hero-line', '<div class="kicker">The usual way</div><div style="margin-top:18px">Every layer,<br>written by hand.</div>');
  const second = el('div', 'layer hero-line', '<div class="kicker">Here</div><div style="margin-top:18px">Declare it once.<br>Generate the rest.</div>');
  first.style.top = second.style.top = '360px';
  const motif = el('div', 'layer motif');
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('width', '520'); svg.setAttribute('height', '440'); svg.style.overflow = 'visible';
  const cells = [];
  for (let r = 0; r < 4; r++) for (let c = 0; c < 5; c++) cells.push([c, r]);
  svg.innerHTML = cells.map(([c, r], i) => `<rect class="m" data-i="${i}" width="64" height="64" rx="10" fill="${i === 7 ? 'var(--claimed)' : 'none'}" stroke="${i === 7 ? 'var(--accent)' : '#e9e9ed'}" stroke-opacity="${i === 7 ? 1 : 0.22}" stroke-width="2"/>`).join('') +
    '<circle class="claim" r="6" fill="var(--accent)"/>';
  motif.appendChild(svg);
  s.append(first, second, motif);
  const jitter = (i, k) => Math.sin(i * 12.9898 + k * 78.233) * 43758.5453 % 1;
  scenes.push((t) => {
    st(first, envelope(t, start + 0.3, 6.7));
    st(second, envelope(t, 6.9, end));
    const snap = outCubic(prog(t, 6.6, 8.0));
    svg.querySelectorAll('.m').forEach((rect) => {
      const i = +rect.dataset.i, [c, r] = cells[i];
      const gx = c * 96, gy = r * 96;
      const wob = Math.sin(t * 1.3 + i) * 6 * (1 - snap);
      const x = gx + (jitter(i, 1) * 120 + wob) * (1 - snap), y = gy + (jitter(i, 2) * 90 - wob) * (1 - snap);
      const rot = jitter(i, 3) * 28 * (1 - snap);
      rect.setAttribute('transform', `translate(${x.toFixed(2)} ${y.toFixed(2)}) rotate(${rot.toFixed(2)} 32 32)`);
      rect.setAttribute('opacity', (outCubic(prog(t, 0.4 + i * 0.08, 1.0 + i * 0.08)) * (i === 7 ? snap : 1)).toFixed(3));
    });
    const claim = svg.querySelector('.claim');
    claim.setAttribute('cx', 2 * 96 + 32); claim.setAttribute('cy', 1 * 96 + 32);
    claim.setAttribute('opacity', snap.toFixed(3));
    st(motif, envelope(t, start, end, 0.6, 0.5));
  });
}

// the four layers: header, the shape before, the declaration, the shape after, then the whole model
for (const name of ['ingest', 'conform', 'integrate', 'serve']) {
  const L = LAYERS[name], s = scene(name), c = chapterOf[name], { start, end, beats } = span[name];
  const close = beats.close_up, far = beats.zoom_out;
  const head = header(`Layer ${L.n} of 4`, L.title, L.sub);
  const prior = { ingest: 'raw', conform: 'raw', integrate: 'contract', serve: 'anchor' }[name];
  const left = side('left', L.before, prior);
  const right = side('right', L.after, L.colour);
  const cards = c.close_up.map((shown) => card(shown, L.colour));
  const wide = zoom(name, L.colour, L.zoom);
  s.append(head, left, ...cards, right, wide);
  cards.forEach(centreCard);
  const per = (close.end - close.start) / cards.length;
  scenes.push((t) => {
    st(head, envelope(t, start, end));
    const out = inCubic(prog(t, far.start - 0.2, far.start + 0.5));
    const sides = outCubic(prog(t, close.start + 0.3, close.start + 1.0)) * (1 - out);
    st(left, { op: sides, x: -(1 - sides) * 30 });
    st(right, { op: sides, x: (1 - sides) * 30 });
    buildShape(left, t, 0, 0, left.kind !== 'feed');
    buildShape(right, t, close.start + 3.5, close.start + 8.5, false);
    if (left.kind === 'feed') buildShape(left, t, 0, 0, true);
    cards.forEach((box, k) => {
      const t0 = close.start + k * per, t1 = k === cards.length - 1 ? far.start + 0.5 : t0 + per;
      const a = outCubic(prog(t, t0 + 0.2, t0 + 0.8)), b = inCubic(prog(t, t1 - 0.5, t1));
      st(box, { op: a * (1 - b), y: (1 - a) * 18, s: 1 - b * 0.03 });
      typeCard(box, t, t0 + 0.5);
    });
    const z = outCubic(prog(t, far.start, far.start + 0.6)) * (1 - inCubic(prog(t, end - 0.45, end)));
    st(wide, { op: z, s: 0.98 + 0.02 * z });
    growZoom(wide, t, far.start);
  });
}

// orchestration: each source in its own run, then one build
{
  const name = 'orchestration', s = scene(name), c = chapterOf[name], { start, end } = span[name];
  const head = header("One schedule", 'Orchestration', 'Every source in its own run, then one build.');
  const box = card(c.close_up[0], 'anchor');
  const left = el('div', 'layer side left'), right = el('div', 'layer side right');
  const sources = c.zoom_out.tiles.filter((tile) => tile.kind === 'source');
  const lsvg = document.createElementNS(NS, 'svg'); lsvg.setAttribute('viewBox', '0 0 340 340');
  const h = Math.min(70, 260 / sources.length);
  lsvg.innerHTML = sources.map((src, i) => `<g class="src" data-i="${i}"><rect x="90" y="${170 - (sources.length * h) / 2 + i * h + 6}" width="${h - 12}" height="${h - 12}" rx="8" fill="var(--surface)" stroke="var(--raw)" stroke-width="2"/>` +
    `<text class="tilename" x="${90 + h}" y="${170 - (sources.length * h) / 2 + i * h + h / 2 + 5}">${esc(src.name)}</text><rect class="bar" x="90" y="${170 - (sources.length * h) / 2 + i * h + h - 2}" height="3" width="0" fill="var(--raw)"/></g>`).join('');
  left.append(lsvg, el('div', 'label', 'EACH SOURCE, ITS OWN RUN'));
  const rsvg = document.createElementNS(NS, 'svg'); rsvg.setAttribute('viewBox', '0 0 340 340');
  rsvg.innerHTML = '<g class="build"><rect x="120" y="120" width="100" height="100" rx="14" fill="var(--claimed)" stroke="var(--accent)" stroke-width="2.4"/><circle cx="170" cy="170" r="7" fill="var(--accent)"/></g>';
  right.append(rsvg, el('div', 'label', 'THEN ONE BUILD'));
  s.append(head, left, box, right);
  centreCard(box);
  scenes.push((t) => {
    const e = envelope(t, start, end);
    st(head, e);
    st(box, envelope(t, start + 0.4, end));
    typeCard(box, t, start + 0.8);
    st(left, envelope(t, start + 0.6, end));
    st(right, envelope(t, start + 0.6, end));
    lsvg.querySelectorAll('.bar').forEach((bar, i) => bar.setAttribute('width', (outCubic(prog(t, start + 2 + i * 0.4, start + 5 + i * 0.4)) * (h - 12)).toFixed(2)));
    const built = outCubic(prog(t, start + 5.5, start + 6.5));
    rsvg.querySelector('.build').setAttribute('opacity', (0.2 + 0.8 * built).toFixed(3));
  });
}

// lockup
{
  const s = scene('lockup'), { start, end } = span.lockup;
  const mark = el('div', 'layer wordmark', 'Declarative Data Platform');
  const tag = el('div', 'layer tagline', 'Declarations in, structure out.');
  const url = el('div', 'layer url', 'github.com/mattiasthalen/declarative-data-platform');
  s.append(mark, tag, url);
  scenes.push((t) => {
    st(mark, envelope(t, start + 0.2, end + 1, 1.0));
    st(tag, envelope(t, start + 0.9, end + 1, 0.8));
    st(url, envelope(t, start + 1.5, end + 1, 0.8));
  });
}

// the chapter steps, top right, from the first layer to orchestration
const steps = ['ingest', 'conform', 'integrate', 'serve'].map((name) => {
  const step = el('div', 'step', `<i></i>${name}`);
  $('steps').appendChild(step);
  return [name, step];
});
const caption = $('caption').querySelector('span');

window.__duration = F.duration;
window.__seek = (t) => {
  for (const [name, { start, end }] of Object.entries(span)) $(name).style.display = t >= start - 0.05 && t < end + 0.05 ? 'block' : 'none';
  for (const draw of scenes) draw(t);
  const shown = prog(t, span.ingest.start - 0.5, span.ingest.start) * (1 - prog(t, span.orchestration.end - 0.5, span.orchestration.end));
  $('steps').style.opacity = shown;
  for (const [name, step] of steps) {
    const now = t >= span[name].start && t < span[name].end;
    step.style.color = now ? COLOUR[LAYERS[name].colour] : t >= span[name].end ? 'var(--label)' : 'var(--muted)';
    step.querySelector('i').style.background = now ? 'var(--claimed)' : 'none';
  }
  const line = F.captions.find((c) => t >= c.start && t < c.end);
  if (line) {
    if (caption.textContent !== line.text) caption.textContent = line.text;
    caption.style.opacity = outCubic(prog(t, line.start, line.start + 0.2)) * (1 - prog(t, line.end - 0.15, line.end));
  } else caption.style.opacity = 0;
  $('glow').style.opacity = 0.7 + 0.3 * Math.sin(t * 0.4);
};

const FAMILIES = ['Inter', 'Spectral', 'JetBrains Mono'];
Promise.all([
  document.fonts.load('26px Inter'), document.fonts.load('500 26px Inter'), document.fonts.load('600 26px Spectral'), document.fonts.load('14px "JetBrains Mono"'),
]).then(() => {
  const missing = FAMILIES.filter((family) => ![...document.fonts].some((f) => f.family.replace(/["']/g, '') === family && f.status === 'loaded'));
  if (missing.length) throw new Error('fonts not loaded: ' + missing.join(', '));
  window.__seek(0);
  window.__ready = true;
});
