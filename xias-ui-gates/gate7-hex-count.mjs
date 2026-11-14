#!/usr/bin/env node
/**
 * xias-ui-gates — gate 7: hardcoded-hex count over the REAL staging-studio
 * source tree (`src/components` + `src/app`), classified as
 *   - token             : the hex is one of the project's own design-token
 *                         values (src/lib/color-tokens.ts, or a hex literal
 *                         declared in src/app/globals.css :root / .dark)
 *   - material-swatch   : the hex belongs to a material-swatch palette
 *                         (src/components/lookbook/material-swatch*.tsx and
 *                         src/app/(dashboard)/projects/[id]/lookbook/
 *                         material-swatch-editor.tsx) — the documented
 *                         exception, because those hexes ARE the swatch data
 *   - other             : everything else (a hardcoded hex that is neither a
 *                         token value nor a material swatch)
 *
 * Usage:
 *   node xias-ui-gates/gate7-hex-count.mjs <path-to-staging-studio-clone>
 * Writes JSON to stdout and to <out> when --out <file> is given.
 */
import fs from "node:fs";
import path from "node:path";

const repoRoot = path.resolve(process.argv[2] ?? ".");
const outIdx = process.argv.indexOf("--out");
const outFile = outIdx !== -1 ? process.argv[outIdx + 1] : null;

const SCAN_DIRS = ["src/components", "src/app"];
const HEX_RE = /#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b/g;

/** Normalise #abc / #aabbcc / #aabbccdd to lowercase 6/8-digit form. */
function normHex(raw) {
  const h = raw.slice(1).toLowerCase();
  if (h.length === 3 || h.length === 4) {
    return "#" + h.split("").map((c) => c + c).join("");
  }
  return "#" + h;
}

function walk(dir, acc = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(p, acc);
    else if (/\.(tsx?|jsx?|css|scss)$/.test(entry.name)) acc.push(p);
  }
  return acc;
}

/** Token palette: src/lib/color-tokens.ts + hex literals in globals.css. */
function collectTokenValues() {
  const values = new Set();
  const tokensFile = path.join(repoRoot, "src/lib/color-tokens.ts");
  if (fs.existsSync(tokensFile)) {
    const src = fs.readFileSync(tokensFile, "utf8");
    for (const m of src.matchAll(/"(#[0-9a-fA-F]{3,8})"/g)) values.add(normHex(m[1]));
  }
  const cssFile = path.join(repoRoot, "src/app/globals.css");
  if (fs.existsSync(cssFile)) {
    const src = fs.readFileSync(cssFile, "utf8");
    for (const m of src.matchAll(HEX_RE)) values.add(normHex(m[0]));
  }
  return values;
}

function isMaterialSwatchFile(rel) {
  return (
    /material-swatch/.test(rel) ||
    /lookbook\/material/.test(rel)
  );
}

const tokenValues = collectTokenValues();
const files = SCAN_DIRS.flatMap((d) => {
  const abs = path.join(repoRoot, d);
  return fs.existsSync(abs) ? walk(abs) : [];
});

const rows = [];
for (const file of files) {
  const rel = path.relative(repoRoot, file);
  const src = fs.readFileSync(file, "utf8");
  const lines = src.split("\n");
  lines.forEach((line, i) => {
    const ms = line.match(HEX_RE);
    if (!ms) return;
    for (const raw of ms) {
      const value = normHex(raw);
      let cls;
      if (isMaterialSwatchFile(rel)) cls = "material-swatch";
      else if (tokenValues.has(value)) cls = "token";
      else cls = "other";
      rows.push({ file: rel, line: i + 1, hex: value, class: cls, text: line.trim().slice(0, 120) });
    }
  });
}

const counts = { token: 0, "material-swatch": 0, other: 0 };
for (const r of rows) counts[r.class] += 1;

const byFile = {};
for (const r of rows) {
  byFile[r.file] ??= { token: 0, "material-swatch": 0, other: 0, total: 0 };
  byFile[r.file][r.class] += 1;
  byFile[r.file].total += 1;
}

const result = {
  repoRoot,
  scannedDirs: SCAN_DIRS,
  filesScanned: files.length,
  totalHexOccurrences: rows.length,
  classified: counts,
  otherByFile: Object.fromEntries(
    Object.entries(byFile)
      .filter(([, v]) => v.other > 0)
      .sort((a, b) => b[1].other - a[1].other)
  ),
  occurrences: rows,
};

const json = JSON.stringify(result, null, 2);
if (outFile) {
  fs.mkdirSync(path.dirname(outFile), { recursive: true });
  fs.writeFileSync(outFile, json);
}
console.log(
  `[gate7] files=${files.length} totalHex=${rows.length} token=${counts.token} material-swatch=${counts["material-swatch"]} other=${counts.other}`
);
