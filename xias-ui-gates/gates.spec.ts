/**
 * xias-ui-gates — Phase 0 slice 1 gate runner (gates 1-4) against the REAL
 * staging-studio screens, run inside the staging-studio hermetic Playwright
 * harness (mock Supabase + mock Browserless + disposable Postgres + local
 * production build). NEVER a synthetic/stand-in screen.
 *
 * Placement (run from the in-worktree clone):
 *   cp xias-ui-gates/gates.spec.ts staging-studio-src/tests/e2e/specs/xias-ui-gates.spec.ts
 *   cd staging-studio-src && npx playwright test tests/e2e/specs/xias-ui-gates.spec.ts
 *
 * The harness's own globalSetup (global-setup.ts) seeds the fixed rows and
 * starts the mocks; playwright.config.ts starts the app under test. This file
 * only ADDS measurement code. The seeded user's `darkMode` column (the app's
 * only theme mechanism, prisma/schema.prisma:27) is flipped through the
 * harness's own Prisma path to reach the dark rows.
 *
 * Results are written as JSON to $XIAS_GATE_OUT (absolute path).
 */
import { test } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";

import { PrismaClient } from "@prisma/client";
import { PrismaPg } from "@prisma/adapter-pg";

import {
  DATABASE_URL,
  E2E_REHEARSAL_PROJECT_ID,
  E2E_USER_ID,
} from "../env";
import { login } from "../helpers";

const AXE_PATH = path.resolve(__dirname, "../../../node_modules/axe-core/axe.min.js");
const OUT = process.env.XIAS_GATE_OUT ?? path.resolve(__dirname, "../../xias-ui-gates-results.json");

const prisma = new PrismaClient({ adapter: new PrismaPg({ connectionString: DATABASE_URL }) });

interface Violation {
  rule: string;
  impact: string;
  selector: string;
  value: string;
  detail?: string;
}

interface CellResult {
  screen: string;
  theme: string;
  viewport: string;
  status: "measured" | "unmeasurable";
  reason?: string;
  url: string;
  axeSeriousCritical: number;
  axeViolations: Violation[];
  contrastViolations: Violation[];
  targetSizeViolations: Violation[];
  overflow?: { overflowPx: number; scrollWidth: number; clientWidth: number; worst?: Violation };
  themeApplied?: boolean;
  darkFallback?: string;
  ms: number;
}

const VIEWPORTS = [
  { name: "1280x800", width: 1280, height: 800 },
  { name: "390x844", width: 390, height: 844 },
];

type Theme = "light" | "dark";

interface ScreenDef {
  name: string;
  path: string;
  auth: boolean;
  /** extra interaction after navigation (e.g. open the focused editor) */
  prepare?: (page: import("@playwright/test").Page) => Promise<void>;
}

const REHEARSAL = `/projects/${E2E_REHEARSAL_PROJECT_ID}`;

const SCREENS: ScreenDef[] = [
  { name: "login", path: "/login", auth: false },
  { name: "projects list", path: "/projects", auth: true },
  { name: "project detail", path: REHEARSAL, auth: true },
  {
    name: "room studio / edit-room",
    path: REHEARSAL,
    auth: true,
    prepare: async (page) => {
      await page
        .locator(".space-y-3", { hasText: "Rehearsal Room" })
        .getByRole("button", { name: "Edit staging" })
        .click();
      await page.getByRole("button", { name: "All rooms", exact: true }).waitFor({ timeout: 20000 });
    },
  },
  {
    name: "lookbook editor",
    path: `${REHEARSAL}/lookbook`,
    auth: true,
    prepare: async (page) => {
      await page.getByRole("button", { name: "Edit", exact: true }).click();
      await page.getByRole("button", { name: "Preview", exact: true }).waitFor({ timeout: 20000 });
    },
  },
  { name: "settings", path: "/settings", auth: true },
];

async function setDarkMode(dark: boolean): Promise<void> {
  await prisma.user.update({ where: { id: E2E_USER_ID }, data: { darkMode: dark } });
}

test.describe.configure({ mode: "serial" });

test("gates 1-4 across the frozen staging-studio screen set", async ({ page }) => {
  test.setTimeout(45 * 60 * 1000);
  const started = Date.now();
  const results: CellResult[] = [];

  // Authenticated session once; the seeded user's darkMode column is the
  // app's only theme mechanism.
  await login(page);

  for (const theme of ["light", "dark"] as Theme[]) {
    await setDarkMode(theme === "dark");
    for (const vp of VIEWPORTS) {
      for (const screen of SCREENS) {
        const t0 = Date.now();
        const cell: CellResult = {
          screen: screen.name,
          theme,
          viewport: vp.name,
          status: "measured",
          url: screen.path,
          axeSeriousCritical: 0,
          axeViolations: [],
          contrastViolations: [],
          targetSizeViolations: [],
          ms: 0,
        };
        try {
          await page.setViewportSize({ width: vp.width, height: vp.height });
          const resp = await page.goto(screen.path, { waitUntil: "domcontentloaded" });
          if (!resp) throw new Error("no navigation response");
          // settle: fonts + images + any client hydration
          await page.waitForTimeout(1200);
          if (screen.prepare) await screen.prepare(page);
          await page.waitForTimeout(800);

          // ---- theme observation -------------------------------------
          const htmlClass = await page.evaluate(() => document.documentElement.className);
          cell.themeApplied = htmlClass.includes("dark");
          if (theme === "dark" && !cell.themeApplied) {
            // The (auth) layout mounts no ThemeProvider, so the seeded
            // darkMode column cannot reach /login. Apply the app's own
            // `.dark` class to <html> (the real dark token set from
            // globals.css) and record that this is how the dark row was
            // reached.
            await page.evaluate(() => document.documentElement.classList.add("dark"));
            await page.waitForTimeout(400);
            cell.darkFallback = "applied .dark class to <html> (auth layout has no ThemeProvider)";
          }

          // ---- gate 1: axe serious/critical --------------------------
          await page.addScriptTag({ path: AXE_PATH });
          const axeRes = await page.evaluate(async () => {
            // @ts-expect-error axe is injected
            const r = await window.axe.run(document, {
              runOnly: {
                type: "tag",
                values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"],
              },
            });
            return r.violations.map((v: any) => ({
              id: v.id,
              impact: v.impact,
              help: v.help,
              nodes: v.nodes.map((n: any) => ({
                target: JSON.stringify(n.target),
                summary: n.failureSummary ?? "",
                html: (n.html ?? "").slice(0, 200),
              })),
            }));
          });
          const serious = axeRes.filter(
            (v: any) => v.impact === "serious" || v.impact === "critical"
          );
          cell.axeSeriousCritical = serious.reduce((n: number, v: any) => n + v.nodes.length, 0);
          cell.axeViolations = serious.flatMap((v: any) =>
            v.nodes.map((n: any) => ({
              rule: v.id,
              impact: v.impact,
              selector: n.target,
              value: `${v.nodes.length} node(s)`,
              detail: `${n.summary} | ${n.html}`,
            }))
          );

          // ---- gates 2, 3, 4: rendered measurements -------------------
          const measured = await page.evaluate(() => {
            // ---------- helpers ----------
            const cssPath = (el: Element): string => {
              if (!(el instanceof Element)) return String(el);
              const parts: string[] = [];
              let cur: Element | null = el;
              while (cur && cur.nodeType === 1 && parts.length < 6) {
                let part = cur.tagName.toLowerCase();
                if (cur.id) {
                  parts.unshift(`#${cur.id}`);
                  break;
                }
                const cls = (cur.getAttribute("class") ?? "")
                  .split(/\s+/)
                  .filter(Boolean)
                  .slice(0, 2);
                if (cls.length) part += `.${cls.join(".")}`;
                const parent: Element | null = cur.parentElement;
                if (parent) {
                  const sameTag = Array.from(parent.children).filter(
                    (c: Element) => c.tagName === cur!.tagName
                  );
                  if (sameTag.length > 1) {
                    part += `:nth-of-type(${sameTag.indexOf(cur) + 1})`;
                  }
                }
                parts.unshift(part);
                cur = parent;
              }
              return parts.join(" > ");
            };
            const parseColor = (s: string) => {
              const m = s.match(/rgba?\(([^)]+)\)/);
              if (!m) return null;
              const p = m[1].split(",").map((x) => parseFloat(x.trim()));
              return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
            };
            const over = (
              fg: { r: number; g: number; b: number; a: number },
              bg: { r: number; g: number; b: number; a: number }
            ) => ({
              r: fg.r * fg.a + bg.r * (1 - fg.a),
              g: fg.g * fg.a + bg.g * (1 - fg.a),
              b: fg.b * fg.a + bg.b * (1 - fg.a),
              a: 1,
            });
            const lum = (c: { r: number; g: number; b: number }) => {
              const f = (v: number) => {
                const s = v / 255;
                return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
              };
              return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
            };
            const ratio = (a: any, b: any) => {
              const l1 = lum(a);
              const l2 = lum(b);
              const hi = Math.max(l1, l2);
              const lo = Math.min(l1, l2);
              return (hi + 0.05) / (lo + 0.05);
            };
            const visible = (el: Element): boolean => {
              const cs = getComputedStyle(el);
              if (cs.visibility === "hidden" || cs.display === "none") return false;
              if (parseFloat(cs.opacity) === 0) return false;
              const r = el.getBoundingClientRect();
              if (r.width < 1 || r.height < 1) return false;
              if (el.getAttribute("aria-hidden") === "true") return false;
              return true;
            };
            const effOpacity = (el: Element): number => {
              let o = 1;
              let cur: Element | null = el;
              while (cur) {
                o *= parseFloat(getComputedStyle(cur).opacity) || 1;
                cur = cur.parentElement;
              }
              return o;
            };
            const effBg = (el: Element) => {
              const chain: Element[] = [];
              let cur: Element | null = el;
              while (cur) {
                chain.unshift(cur);
                cur = cur.parentElement;
              }
              let acc: any = null;
              let image = false;
              for (const node of chain) {
                const cs = getComputedStyle(node);
                if (cs.backgroundImage && cs.backgroundImage !== "none") image = true;
                const c = parseColor(cs.backgroundColor);
                if (!c || c.a === 0) continue;
                acc = acc ? over(c, acc) : c;
                if (acc.a >= 1) break;
              }
              const canvas = { r: 255, g: 255, b: 255, a: 1 };
              return { bg: acc ? over(acc, canvas) : canvas, image };
            };
            const ownText = (el: Element): string => {
              let t = "";
              el.childNodes.forEach((n) => {
                if (n.nodeType === 3) t += n.textContent ?? "";
              });
              return t.trim();
            };
            const INTERACTIVE =
              'button, a[href], input:not([type="hidden"]), select, textarea, [role="button"], [role="link"], [role="checkbox"], [role="radio"], [role="tab"], [role="switch"], [role="menuitem"], [role="option"], summary, label[for], [tabindex]:not([tabindex="-1"])';

            // ---------- gate 2: rendered contrast ----------
            const contrast: any[] = [];
            document.querySelectorAll<HTMLElement>("*").forEach((el) => {
              const txt = ownText(el);
              if (!txt) return;
              if (!visible(el)) return;
              const cs = getComputedStyle(el);
              if (cs.backgroundImage && cs.backgroundImage !== "none") return; // gradient: not measurable
              if ((el as any).disabled || el.getAttribute("aria-disabled") === "true") return;
              const { bg, image } = effBg(el);
              if (image) return;
              const fgRaw = parseColor(cs.color);
              if (!fgRaw) return;
              const op = effOpacity(el);
              const fg = { ...fgRaw, a: fgRaw.a * op };
              const fgFlat = over(fg, bg);
              const r = ratio(fgFlat, bg);
              const size = parseFloat(cs.fontSize);
              const weight = parseInt(cs.fontWeight, 10) || 400;
              const large = size >= 24 || (size >= 18.66 && weight >= 700);
              const required = large ? 3.0 : 4.5;
              if (r + 0.005 < required) {
                contrast.push({
                  selector: cssPath(el),
                  ratio: Number(r.toFixed(2)),
                  required,
                  large,
                  fontSize: size,
                  fontWeight: weight,
                  fg: `rgb(${Math.round(fgFlat.r)}, ${Math.round(fgFlat.g)}, ${Math.round(fgFlat.b)})`,
                  bg: `rgb(${Math.round(bg.r)}, ${Math.round(bg.g)}, ${Math.round(bg.b)})`,
                  text: txt.slice(0, 60),
                });
              }
            });

            // ---------- gate 3: target size (WCAG 2.5.8, 24x24) ----------
            const targets: any[] = [];
            document.querySelectorAll<HTMLElement>(INTERACTIVE).forEach((el) => {
              if (!visible(el)) return;
              const r = el.getBoundingClientRect();
              const w = Math.round(r.width * 10) / 10;
              const h = Math.round(r.height * 10) / 10;
              if (w < 24 || h < 24) {
                const cs = getComputedStyle(el);
                const cls = el.getAttribute("class") ?? "";
                const label = (
                  el.getAttribute("aria-label") ??
                  ownText(el) ??
                  el.textContent ??
                  ""
                ).trim();
                targets.push({
                  selector: cssPath(el),
                  width: w,
                  height: h,
                  tag: el.tagName.toLowerCase(),
                  label: label.slice(0, 40),
                  bg: cs.backgroundColor,
                  cls: cls.slice(0, 80),
                });
              }
            });

            // ---------- gate 4: horizontal overflow ----------
            const de = document.documentElement;
            const clientWidth = de.clientWidth;
            const scrollWidth = Math.max(de.scrollWidth, document.body.scrollWidth);
            const overflowPx = scrollWidth - clientWidth;
            const offenders: any[] = [];
            if (overflowPx > 0) {
              document.querySelectorAll<HTMLElement>("*").forEach((el) => {
                if (!visible(el)) return;
                const r = el.getBoundingClientRect();
                if (r.width <= 0) return;
                if (r.right > clientWidth + 1) {
                  offenders.push({
                    selector: cssPath(el),
                    right: Math.round(r.right),
                    width: Math.round(r.width),
                    scrollWidth: el.scrollWidth,
                  });
                }
              });
              offenders.sort((a, b) => b.right - a.right);
            }

            return { contrast, targets, overflow: { clientWidth, scrollWidth, overflowPx, offenders } };
          });

          cell.contrastViolations = measured.contrast.map((c: any) => ({
            rule: "rendered-contrast",
            impact: c.large ? "moderate" : "serious",
            selector: c.selector,
            value: `${c.ratio}:1 (needs ${c.required}:1, ${c.fontSize}px/${c.fontWeight})`,
            detail: `fg ${c.fg} on bg ${c.bg} — "${c.text}"`,
          }));
          cell.targetSizeViolations = measured.targets.map((t: any) => ({
            rule: "target-size",
            impact: "serious",
            selector: t.selector,
            value: `${t.width}x${t.height} (needs 24x24)`,
            detail: `${t.tag} "${t.label}" bg ${t.bg} class "${t.cls}"`,
          }));
          cell.overflow = {
            overflowPx: measured.overflow.overflowPx,
            scrollWidth: measured.overflow.scrollWidth,
            clientWidth: measured.overflow.clientWidth,
            worst: measured.overflow.offenders[0]
              ? {
                  rule: "horizontal-overflow",
                  impact: "serious",
                  selector: measured.overflow.offenders[0].selector,
                  value: `right=${measured.overflow.offenders[0].right} width=${measured.overflow.offenders[0].width} (viewport ${measured.overflow.clientWidth})`,
                  detail: `document scrollWidth ${measured.overflow.scrollWidth} > clientWidth ${measured.overflow.clientWidth}`,
                }
              : undefined,
          };
        } catch (err) {
          cell.status = "unmeasurable";
          cell.reason = String((err as Error).message ?? err).slice(0, 300);
        }
        cell.ms = Date.now() - t0;
        results.push(cell);
        console.log(
          `[xias-gate] ${screen.name} | ${theme} | ${vp.name} | axe=${cell.axeSeriousCritical} contrast=${cell.contrastViolations.length} target=${cell.targetSizeViolations.length} overflow=${cell.overflow?.overflowPx ?? "n/a"} (${cell.ms}ms)`
        );
      }
    }
  }

  const wallMs = Date.now() - started;
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(
    OUT,
    JSON.stringify({ wallMs, results, generatedAt: new Date().toISOString() }, null, 2)
  );
  console.log(`[xias-gate] wall-time ${wallMs}ms -> ${OUT}`);
});
