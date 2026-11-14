# XIAS UI gates — Phase 0 report (POC #46 / issue #54)

Two surfaces are measured in this report:

- **staging-studio app** (slice 1, issue #54) — automated rendered-UI gates 1–4 + 7 measured against the real staging-studio app in its own hermetic Playwright harness (seeded user + rehearsal project, mocked providers). No staging-studio code changes; no fixes; measurement only. This is the surface the recorded verdict rests on.
- **generative-ui-diagnostic-lens renderer** (slice 2, this section) — the same gates 1–4 measured against the static HTML the lens renderer produces for its three fixture cases, with a stdlib-only Python script. See "Lens surface" below.

Nothing in the lens section changes the recorded whole-spike verdict; it only makes the previously prose-only lens half reproducible.

- staging-studio commit measured: `44c62048ca47a5ec7c449740979fefc09bdac776` (develop tip at measurement time)
- Screens: login, projects list, project detail, room studio / edit-room, lookbook editor, settings × light/dark × 1280×800 / 390×844 = 24 cells, all `measured` (0 unmeasurable).
- Gates 1–4 wall-time: **71688 ms** (single Playwright run, incl. app build + seed via global setup; per-cell times in results JSON). Gate 7 wall-time: not recorded by the counting script.
- Dark theme driven by the seeded user's persisted `darkMode` preference (the mechanism the app itself uses); where the auth layout has no ThemeProvider the runner records a `.dark`-class fallback per cell in the results JSON (`darkFallback`).
- Environment adaptations on this VM (measurement-only, in the scratch clone, not in any deliverable): Docker is unavailable, so the harness's global setup was pointed at an already-running local PostgreSQL 16 (127.0.0.1:39921, same seeded fixtures); Prisma's schema-engine was supplied from the local Prisma cache because the engine download is blocked here. Neither changes what is rendered or measured.

## Raw table — gates 1–4 (counts per cell; worst example per gate)

| Screen | Theme | Viewport | G1 axe s/c | G2 contrast | G3 target | G4 overflow px | Worst G1 | Worst G2 | Worst G3 |
|---|---|---|---|---|---|---|---|---|---|
| login | light | 1280x800 | 9 | 14 | 1 | 0 | color-contrast (serious) ["div > .leading-relaxed.mt-1"] | 1.05:1 (needs 4.5:1, 14px/500) @  > div.mb-8.flex:nth-of-type(1) > a.group/button.inline-flex | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| projects list | light | 1280x800 | 9 | 14 | 1 | 0 | color-contrast (serious) ["div > .leading-relaxed.mt-1"] | 1.05:1 (needs 4.5:1, 14px/500) @  > div.mb-8.flex:nth-of-type(1) > a.group/button.inline-flex | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| project detail | light | 1280x800 | 19 | 25 | 13 | 0 | color-contrast (serious) ["a[href$=\"projects\"]"] | 1:1 (needs 4.5:1, 16px/400) @ type(1) > span.absolute.left-1:nth-of-type(1) > span.sr-only | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| room studio / edit-room | light | 1280x800 | 7 | 5 | 3 | 0 | color-contrast (serious) ["a[href$=\"projects\"]"] | 1.05:1 (needs 4.5:1, 12px/400) @ able.GNMova_variable > body.antialiased > div:nth-of-type(4) | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| lookbook editor | light | 1280x800 | 24 | 29 | 20 | 0 | color-contrast (serious) [".paper-preview:nth-child(1) > .p-12.lookbook-page.min-h-sc | 1.05:1 (needs 4.5:1, 14px/500) @ unded-md:nth-of-type(1) > button.rounded.px-4:nth-of-type(1) | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| settings | light | 1280x800 | 5 | 7 | 6 | 0 | color-contrast (serious) ["label[for=\"logo\"] > .text-muted-foreground"] | 1.05:1 (needs 4.5:1, 14px/500) @  > form.max-w-md.space-y-8 > button.group/button.inline-flex | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| login | light | 390x844 | 8 | 25 | 1 | 0 | color-contrast (serious) ["div > .leading-relaxed.mt-1"] | 1.05:1 (needs 4.5:1, 14px/500) @  > div.mb-8.flex:nth-of-type(1) > a.group/button.inline-flex | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| projects list | light | 390x844 | 8 | 25 | 1 | 0 | color-contrast (serious) ["div > .leading-relaxed.mt-1"] | 1.05:1 (needs 4.5:1, 14px/500) @  > div.mb-8.flex:nth-of-type(1) > a.group/button.inline-flex | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| project detail | light | 390x844 | 17 | 34 | 13 | 0 | color-contrast (serious) [".px-2\\.5"] | 1:1 (needs 4.5:1, 16px/400) @ type(1) > span.absolute.left-1:nth-of-type(1) > span.sr-only | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| room studio / edit-room | light | 390x844 | 3 | 13 | 2 | 0 | color-contrast (serious) [".rounded-full"] | 1.05:1 (needs 4.5:1, 12px/400) @ able.GNMova_variable > body.antialiased > div:nth-of-type(4) | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| lookbook editor | light | 390x844 | 13 | 41 | 20 | 0 | color-contrast (serious) [".paper-preview:nth-child(1) > .p-12.lookbook-page.min-h-sc | 1.05:1 (needs 4.5:1, 14px/500) @ unded-md:nth-of-type(1) > button.rounded.px-4:nth-of-type(1) | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| settings | light | 390x844 | 5 | 18 | 6 | 0 | color-contrast (serious) ["label[for=\"logo\"] > .text-muted-foreground"] | 1.05:1 (needs 4.5:1, 14px/500) @  > form.max-w-md.space-y-8 > button.group/button.inline-flex | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| login | dark | 1280x800 | 0 | 0 | 1 | 0 | — | — | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| projects list | dark | 1280x800 | 0 | 0 | 1 | 0 | — | — | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| project detail | dark | 1280x800 | 15 | 0 | 13 | 0 | color-contrast (serious) [".bg-surface-container-low\\/50.border-outline-variant\\/30 | — | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| room studio / edit-room | dark | 1280x800 | 2 | 0 | 3 | 0 | color-contrast (serious) [".h-96 > .font-medium.text-sm"] | — | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| lookbook editor | dark | 1280x800 | 56 | 8 | 20 | 0 | color-contrast (serious) [".mb-6.no-print.justify-between > div > h1"] | 1:1 (needs 4.5:1, 14px/500) @ unded-md:nth-of-type(1) > button.rounded.px-4:nth-of-type(1) | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| settings | dark | 1280x800 | 2 | 0 | 6 | 0 | color-contrast (serious) ["h1"] | — | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| login | dark | 390x844 | 0 | 0 | 1 | 0 | — | — | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| projects list | dark | 390x844 | 0 | 0 | 1 | 0 | — | — | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| project detail | dark | 390x844 | 15 | 0 | 13 | 0 | color-contrast (serious) [".bg-surface-container-low\\/50.border-outline-variant\\/30 | — | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| room studio / edit-room | dark | 390x844 | 1 | 0 | 2 | 0 | color-contrast (serious) [".text-stone-400.text-xs"] | — | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| lookbook editor | dark | 390x844 | 36 | 8 | 20 | 0 | color-contrast (serious) [".mb-6.no-print.justify-between > div > h1"] | 1:1 (needs 4.5:1, 14px/500) @ unded-md:nth-of-type(1) > button.rounded.px-4:nth-of-type(1) | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |
| settings | dark | 390x844 | 2 | 0 | 6 | 0 | color-contrast (serious) ["h1"] | — | 1x1 (needs 24x24) @ v.flex.h-screen:nth-of-type(2) > a.sr-only.focus:not-sr-only |

Gate totals (summed over cells): G1 axe serious/critical nodes = **256**, G2 rendered-contrast violations = **266**, G3 target-size violations = **174**, G4 overflow = **0 px** in every cell (no horizontal overflow at 390px on these screens).

## P1-class findings (individual, de-duplicated across themes/viewports per screen)

P1 class per the parent gate: axe serious/critical, rendered contrast < AA, target < 24×24. Overflow at 390px: none found on any screen.
### login — 44 unique P1 findings
- [color-contrast] `[".mt-5 > .gap-2.flex.items-center > .h-6.px-2\\.5.py-1"]` — 8 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".mt-5 > .gap-2.flex.items-center > .h-6.px-2\\.5.py-1"]` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".p-5.border-amber-200.bg-gradient-to-br:nth-child(2) > .mt-3.justify-between.flex > .gap-2.flex.items-center` — 8 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-5.border-amber-200.bg-gradient-to-br:nth-child(2) > .mt-3.justify-between.flex > .gap-2.flex.items-center` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-5.border-amber-200.bg-gradient-to-br:nth-child(3) > .mt-3.justify-between.flex > .gap-2.flex.items-center` — 8 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-5.border-amber-200.bg-gradient-to-br:nth-child(3) > .mt-3.justify-between.flex > .gap-2.flex.items-center` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-5.border-amber-200.bg-gradient-to-br:nth-child(4) > .mt-3.justify-between.flex > .gap-2.flex.items-center` — 8 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-5.border-amber-200.bg-gradient-to-br:nth-child(4) > .mt-3.justify-between.flex > .gap-2.flex.items-center` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-5.border-amber-200.bg-gradient-to-br:nth-child(5) > .mt-3.justify-between.flex > .gap-2.flex.items-center` — 8 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-5.border-amber-200.bg-gradient-to-br:nth-child(5) > .mt-3.justify-between.flex > .gap-2.flex.items-center` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".sm\\:inline"]` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".text-base"]` — 8 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 12.0pt (16px), font weight: normal). E
- [color-contrast] `[".text-base"]` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 12.0pt (16px), font weight: normal). E
- [color-contrast] `[".text-center"]` — 8 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.77 (foreground color: #181716, background color: #8f4d20, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".text-center"]` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.77 (foreground color: #181716, background color: #8f4d20, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["div > .leading-relaxed.mt-1"]` — 8 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["div > .leading-relaxed.mt-1"]` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 10.5pt (14px), font weight: normal). E
- [rendered-contrast] `#main-content > div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(1) > p.mt-1.text-muted-` — 3.58:1 (needs 4.5:1, 16px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Upload Client"
- [rendered-contrast] `#main-content > div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(2) > p.mt-1.text-muted-` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Editor Client"
- [rendered-contrast] `#main-content > div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(3) > p.mt-1.text-muted-` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Concept Client"
- [rendered-contrast] `#main-content > div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(4) > p.mt-1.text-muted-` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Rehearsal Client"
- [rendered-contrast] `#main-content > div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(5) > p.mt-1.text-muted-` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Signoff Client"
- [rendered-contrast] `#main-content > div.p-8 > div.mb-8.flex:nth-of-type(1) > a.group/button.inline-flex` — 1.05:1 (needs 4.5:1, 14px/500) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "+ New Project"
- [rendered-contrast] `#main-content > div.p-8 > div.mb-8.flex:nth-of-type(1) > div > p.mt-1.text-sm` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Manage your staging lookbooks"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(1) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Upload Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(1) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "101 Upload Lane"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(2) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Editor Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(2) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "202 Editor Court"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(3) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Concept Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(3) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "404 Concept Crescent"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(4) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Rehearsal Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(4) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "303 Rehearsal Road"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(5) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Signoff Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(5) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "505 Signature Way"
- [rendered-contrast] `div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(1) > div.flex.items-center:nth-of-type(` — 3.58:1 (needs 4.5:1, 14px/500) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Organic Modern Luxury"
- [rendered-contrast] `div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(2) > div.flex.items-center:nth-of-type(` — 3.58:1 (needs 4.5:1, 12px/500) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Warm Transitional"
- [rendered-contrast] `div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(3) > div.flex.items-center:nth-of-type(` — 3.58:1 (needs 4.5:1, 12px/500) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Vintage Modern"
- [rendered-contrast] `div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(4) > div.flex.items-center:nth-of-type(` — 3.58:1 (needs 4.5:1, 12px/500) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Vintage Modern"
- [rendered-contrast] `div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(5) > div.flex.items-center > div.flex.i` — 3.58:1 (needs 4.5:1, 12px/500) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Organic Modern Luxury"
- [rendered-contrast] `div.p-8 > div.mb-6:nth-of-type(2) > div.space-y-3 > div.flex.items-center > button.flex.h-9 > span.hidden.sm:i` — 3.58:1 (needs 4.5:1, 14px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Filters"
- [rendered-contrast] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div.flex.h-screen:nth-of-type(2) > aside.no-print.fi` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Settings"
- [rendered-contrast] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div.flex.h-screen:nth-of-type(2) > aside.no-print.fi` — 3.58:1 (needs 4.5:1, 12px/600) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Projects"
- [rendered-contrast] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div:nth-of-type(4)` — 1.05:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "agentation: disconnected"
- [target-size] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div.flex.h-screen:nth-of-type(2) > a.sr-only.focus:n` — 1x1 (needs 24x24) (in 4 cell(s)) — a "Skip to main content" bg rgba(0, 0, 0, 0) class "sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:"

### projects list — 44 unique P1 findings
- [color-contrast] `[".mt-5 > .gap-2.flex.items-center > .h-6.px-2\\.5.py-1"]` — 8 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".mt-5 > .gap-2.flex.items-center > .h-6.px-2\\.5.py-1"]` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".p-5.border-amber-200.bg-gradient-to-br:nth-child(2) > .mt-3.justify-between.flex > .gap-2.flex.items-center` — 8 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-5.border-amber-200.bg-gradient-to-br:nth-child(2) > .mt-3.justify-between.flex > .gap-2.flex.items-center` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-5.border-amber-200.bg-gradient-to-br:nth-child(3) > .mt-3.justify-between.flex > .gap-2.flex.items-center` — 8 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-5.border-amber-200.bg-gradient-to-br:nth-child(3) > .mt-3.justify-between.flex > .gap-2.flex.items-center` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-5.border-amber-200.bg-gradient-to-br:nth-child(4) > .mt-3.justify-between.flex > .gap-2.flex.items-center` — 8 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-5.border-amber-200.bg-gradient-to-br:nth-child(4) > .mt-3.justify-between.flex > .gap-2.flex.items-center` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-5.border-amber-200.bg-gradient-to-br:nth-child(5) > .mt-3.justify-between.flex > .gap-2.flex.items-center` — 8 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-5.border-amber-200.bg-gradient-to-br:nth-child(5) > .mt-3.justify-between.flex > .gap-2.flex.items-center` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".sm\\:inline"]` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".text-base"]` — 8 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 12.0pt (16px), font weight: normal). E
- [color-contrast] `[".text-base"]` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 12.0pt (16px), font weight: normal). E
- [color-contrast] `[".text-center"]` — 8 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.77 (foreground color: #181716, background color: #8f4d20, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".text-center"]` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.77 (foreground color: #181716, background color: #8f4d20, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["div > .leading-relaxed.mt-1"]` — 8 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["div > .leading-relaxed.mt-1"]` — 9 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 10.5pt (14px), font weight: normal). E
- [rendered-contrast] `#main-content > div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(1) > p.mt-1.text-muted-` — 3.58:1 (needs 4.5:1, 16px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Upload Client"
- [rendered-contrast] `#main-content > div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(2) > p.mt-1.text-muted-` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Editor Client"
- [rendered-contrast] `#main-content > div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(3) > p.mt-1.text-muted-` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Concept Client"
- [rendered-contrast] `#main-content > div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(4) > p.mt-1.text-muted-` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Rehearsal Client"
- [rendered-contrast] `#main-content > div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(5) > p.mt-1.text-muted-` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Signoff Client"
- [rendered-contrast] `#main-content > div.p-8 > div.mb-8.flex:nth-of-type(1) > a.group/button.inline-flex` — 1.05:1 (needs 4.5:1, 14px/500) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "+ New Project"
- [rendered-contrast] `#main-content > div.p-8 > div.mb-8.flex:nth-of-type(1) > div > p.mt-1.text-sm` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Manage your staging lookbooks"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(1) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Upload Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(1) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "101 Upload Lane"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(2) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Editor Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(2) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "202 Editor Court"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(3) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Concept Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(3) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "404 Concept Crescent"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(4) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Rehearsal Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(4) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "303 Rehearsal Road"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(5) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Signoff Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(5) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "505 Signature Way"
- [rendered-contrast] `div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(1) > div.flex.items-center:nth-of-type(` — 3.58:1 (needs 4.5:1, 14px/500) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Organic Modern Luxury"
- [rendered-contrast] `div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(2) > div.flex.items-center:nth-of-type(` — 3.58:1 (needs 4.5:1, 12px/500) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Warm Transitional"
- [rendered-contrast] `div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(3) > div.flex.items-center:nth-of-type(` — 3.58:1 (needs 4.5:1, 12px/500) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Vintage Modern"
- [rendered-contrast] `div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(4) > div.flex.items-center:nth-of-type(` — 3.58:1 (needs 4.5:1, 12px/500) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Vintage Modern"
- [rendered-contrast] `div.p-8 > div.grid.gap-4:nth-of-type(3) > a.group.relative:nth-of-type(5) > div.flex.items-center > div.flex.i` — 3.58:1 (needs 4.5:1, 12px/500) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Organic Modern Luxury"
- [rendered-contrast] `div.p-8 > div.mb-6:nth-of-type(2) > div.space-y-3 > div.flex.items-center > button.flex.h-9 > span.hidden.sm:i` — 3.58:1 (needs 4.5:1, 14px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Filters"
- [rendered-contrast] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div.flex.h-screen:nth-of-type(2) > aside.no-print.fi` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Settings"
- [rendered-contrast] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div.flex.h-screen:nth-of-type(2) > aside.no-print.fi` — 3.58:1 (needs 4.5:1, 12px/600) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Projects"
- [rendered-contrast] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div:nth-of-type(4)` — 1.05:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "agentation: disconnected"
- [target-size] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div.flex.h-screen:nth-of-type(2) > a.sr-only.focus:n` — 1x1 (needs 24x24) (in 4 cell(s)) — a "Skip to main content" bg rgba(0, 0, 0, 0) class "sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:"

### project detail — 99 unique P1 findings
- [color-contrast] `["#project-aesthetic-helper"]` — 15 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.32 (foreground color: #a1a1a1, background color: #f8f2ed, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `["#project-aesthetic-helper"]` — 17 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `["#project-aesthetic-helper"]` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".bg-surface-container-low\\/50.border-outline-variant\\/30.flex-wrap:nth-child(1) > .text-sm.text-muted-fore` — 15 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.32 (foreground color: #a1a1a1, background color: #f8f2ed, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".bg-surface-container-low\\/50.border-outline-variant\\/30.flex-wrap:nth-child(1) > .text-sm.text-muted-fore` — 17 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".bg-surface-container-low\\/50.border-outline-variant\\/30.flex-wrap:nth-child(1) > .text-sm.text-muted-fore` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".bg-surface-container-low\\/50.border-outline-variant\\/30.flex-wrap:nth-child(2) > .text-sm.text-muted-fore` — 15 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.32 (foreground color: #a1a1a1, background color: #f8f2ed, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".bg-surface-container-low\\/50.border-outline-variant\\/30.flex-wrap:nth-child(2) > .text-sm.text-muted-fore` — 17 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".bg-surface-container-low\\/50.border-outline-variant\\/30.flex-wrap:nth-child(2) > .text-sm.text-muted-fore` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".bg-surface-container-low\\/50.border-outline-variant\\/30.flex-wrap:nth-child(3) > .text-sm.text-muted-fore` — 15 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.32 (foreground color: #a1a1a1, background color: #f8f2ed, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".bg-surface-container-low\\/50.border-outline-variant\\/30.flex-wrap:nth-child(3) > .text-sm.text-muted-fore` — 17 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".bg-surface-container-low\\/50.border-outline-variant\\/30.flex-wrap:nth-child(3) > .text-sm.text-muted-fore` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".bg-surface-container-low\\/50.border-outline-variant\\/30.flex-wrap:nth-child(4) > .text-sm.text-muted-fore` — 15 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.32 (foreground color: #a1a1a1, background color: #f8f2ed, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".bg-surface-container-low\\/50.border-outline-variant\\/30.flex-wrap:nth-child(4) > .text-sm.text-muted-fore` — 17 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".bg-surface-container-low\\/50.border-outline-variant\\/30.flex-wrap:nth-child(4) > .text-sm.text-muted-fore` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".bg-surface-container-low\\/50.border-outline-variant\\/30.flex-wrap:nth-child(4) > .text-xs.text-muted-fore` — 15 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.32 (foreground color: #a1a1a1, background color: #f8f2ed, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".bg-surface-container-low\\/50.border-outline-variant\\/30.flex-wrap:nth-child(4) > .text-xs.text-muted-fore` — 17 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".bg-surface-container-low\\/50.border-outline-variant\\/30.flex-wrap:nth-child(4) > .text-xs.text-muted-fore` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".flex-col.gap-1.flex > .gap-1\\.5.flex.items-center > .text-foreground.text-xs"]` — 15 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.06 (foreground color: #fafafa, background color: #f8f2ed, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".flex-col.gap-1.flex > .gap-1\\.5.flex.items-center > .text-xs.text-muted-foreground"]` — 15 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.32 (foreground color: #a1a1a1, background color: #f8f2ed, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".flex-col.gap-1.flex > .gap-1\\.5.flex.items-center > .text-xs.text-muted-foreground"]` — 17 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".flex-col.gap-1.flex > .gap-1\\.5.flex.items-center > .text-xs.text-muted-foreground"]` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".font-jakarta"]` — 17 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".font-jakarta"]` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".font-mono"]` — 15 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.06 (foreground color: #fafafa, background color: #f8f2ed, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".gap-0\\.5"]` — 15 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.32 (foreground color: #a1a1a1, background color: #f8f2ed, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".gap-0\\.5"]` — 17 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".gap-0\\.5"]` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".gap-2.flex.items-center > .text-xs.text-muted-foreground:nth-child(1)"]` — 15 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.32 (foreground color: #a1a1a1, background color: #f8f2ed, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".gap-2.flex.items-center > .text-xs.text-muted-foreground:nth-child(1)"]` — 17 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".gap-2.flex.items-center > .text-xs.text-muted-foreground:nth-child(1)"]` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.56 (foreground color: #8c827a, background color: #fef8f3, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".h-64 > .font-medium.text-sm"]` — 15 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 4.38 (foreground color: #79716b, background color: #f5f5f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".h-64 > .font-medium.text-sm"]` — 17 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 4.38 (foreground color: #79716b, background color: #f5f5f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".h-64 > .font-medium.text-sm"]` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 4.38 (foreground color: #79716b, background color: #f5f5f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".justify-end > .text-xs.text-muted-foreground:nth-child(2)"]` — 15 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.32 (foreground color: #a1a1a1, background color: #f3f3f3, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".justify-end > .text-xs.text-muted-foreground:nth-child(2)"]` — 17 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #fffffe, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".justify-end > .text-xs.text-muted-foreground:nth-child(2)"]` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #fffffe, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".justify-end > .text-xs.text-muted-foreground:nth-child(4)"]` — 15 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.32 (foreground color: #a1a1a1, background color: #f3f3f3, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".justify-end > .text-xs.text-muted-foreground:nth-child(4)"]` — 17 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #fffffe, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".justify-end > .text-xs.text-muted-foreground:nth-child(4)"]` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #fffffe, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".px-1"]` — 17 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 7.5pt (10px), font weight: normal). Ex
- [color-contrast] `[".px-1"]` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.48 (foreground color: #8c827a, background color: #f8f6f2, font size: 7.5pt (10px), font weight: normal). Ex
- [color-contrast] `[".px-2\\.5"]` — 17 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.77 (foreground color: #181716, background color: #8f4d20, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".px-2\\.5"]` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.77 (foreground color: #181716, background color: #8f4d20, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".sm\\:inline"]` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".snap-start.shrink-0.w-44:nth-child(1) > .text-xs.text-muted-foreground"]` — 17 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".snap-start.shrink-0.w-44:nth-child(1) > .text-xs.text-muted-foreground"]` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".text-stone-400.text-xs"]` — 15 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.36 (foreground color: #a6a09b, background color: #f5f5f4, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".text-stone-400.text-xs"]` — 17 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.36 (foreground color: #a6a09b, background color: #f5f5f4, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".text-stone-400.text-xs"]` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.36 (foreground color: #a6a09b, background color: #f5f5f4, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `["a[href$=\"projects\"]"]` — 19 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 10.5pt (14px), font weight: normal). E
- [rendered-contrast] `#main-content > div.min-h-screen.bg-background > header.shrink-0.bg-background > div.flex.items-center > div.f` — 3.58:1 (needs 4.5:1, 14px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "· Rehearsal Client"
- [rendered-contrast] `#main-content > div.min-h-screen.bg-background > main.p-8 > div.flex.items-center:nth-of-type(1) > button.inli` — 1.05:1 (needs 4.5:1, 14px/500) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "Add rooms"
- [rendered-contrast] `#main-content > div.min-h-screen.bg-background > main.p-8 > div.sticky.top-0:nth-of-type(2) > div.flex.flex-wr` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Coming soon"
- [rendered-contrast] `#main-content > div.min-h-screen.bg-background > main.p-8 > div.sticky.top-0:nth-of-type(2) > div.flex.flex-wr` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Coming soon"
- [rendered-contrast] `#project-aesthetic-helper` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Every room is staged in this style."
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(1) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Upload Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(1) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "101 Upload Lane"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(2) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Editor Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(2) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "202 Editor Court"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(3) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Concept Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(3) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "404 Concept Crescent"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(5) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Signoff Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(5) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "505 Signature Way"
- [rendered-contrast] `div.flex.snap-x:nth-of-type(4) > div.flex.w-44:nth-of-type(2) > span.relative.block:nth-of-type(1) > button.re` — 1:1 (needs 4.5:1, 16px/400) (in 2 cell(s)) — fg rgb(255, 248, 244) on bg rgb(255, 248, 244) — "(Selected)"
- [rendered-contrast] `div.flex.snap-x:nth-of-type(4) > div.flex.w-44:nth-of-type(3) > span.relative.block:nth-of-type(1) > button.re` — 3.58:1 (needs 4.5:1, 10px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Not staged yet"
- [rendered-contrast] `div.min-h-screen.bg-background > header.shrink-0.bg-background > div.flex.items-center > div.flex.min-w-0:nth-` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Projects"
- [rendered-contrast] `div.min-h-screen.bg-background > main.p-8 > div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Project aesthetic"
- [rendered-contrast] `div.min-h-screen.bg-background > main.p-8 > div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Preserve"
- [rendered-contrast] `div.min-h-screen.bg-background > main.p-8 > div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Realism & Lighting"
- [rendered-contrast] `div.min-h-screen.bg-background > main.p-8 > div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Render Status"
- [rendered-contrast] `div.min-h-screen.bg-background > main.p-8 > div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Coming soon"
- [rendered-contrast] `div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type(1) > div.flex.flex-wrap:nth-of-type(2) > di` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "×"
- [rendered-contrast] `div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type(1) > div.flex.flex-wrap:nth-of-type(2) > di` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "×"
- [rendered-contrast] `div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type(1) > div.flex.flex-wrap:nth-of-type(2) > di` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "×"
- [rendered-contrast] `div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type(1) > div.flex.flex-wrap:nth-of-type(4) > di` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "2 rooms"
- [rendered-contrast] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div.flex.h-screen:nth-of-type(2) > aside.no-print.fi` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Settings"
- [rendered-contrast] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div.flex.h-screen:nth-of-type(2) > aside.no-print.fi` — 3.58:1 (needs 4.5:1, 12px/600) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Projects"
- [rendered-contrast] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div:nth-of-type(4)` — 1.05:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "agentation: disconnected"
- [rendered-contrast] `main.p-8 > div.grid.gap-8:nth-of-type(3) > div.space-y-3.rounded-lg:nth-of-type(2) > div.flex.snap-x:nth-of-ty` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Original"
- [rendered-contrast] `main.p-8 > div.grid.gap-8:nth-of-type(3) > div.space-y-3.rounded-lg:nth-of-type(2) > div.flex.snap-x:nth-of-ty` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Variant B"
- [rendered-contrast] `main.p-8 > div.grid.gap-8:nth-of-type(3) > div.space-y-3.rounded-lg:nth-of-type(2) > div.relative.w-full:nth-o` — 1.05:1 (needs 4.5:1, 11px/600) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "Variant A — staged"
- [rendered-contrast] `main.p-8 > div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type(1) > div.flex.flex-wrap:nth-of-t` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "+ Add"
- [rendered-contrast] `main.p-8 > div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type(1) > div.flex.flex-wrap:nth-of-t` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Artistic"
- [rendered-contrast] `main.p-8 > div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type(1) > div.flex.flex-wrap:nth-of-t` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Photorealistic"
- [rendered-contrast] `main.p-8 > section.mb-8 > div.rounded-lg.border > label.flex.items-start > span.flex-1 > span.mt-1.block:nth-o` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Adds a small disclosure label to every AI-staged after-image"
- [target-size] `#virtually-staged-label-toggle` — 16x16 (needs 24x24) (in 4 cell(s)) — input "" bg rgba(0, 0, 0, 0) class "mt-1 h-4 w-4 rounded border-input text-primary accent-primary"
- [target-size] `div.min-h-screen.bg-background > header.shrink-0.bg-background > div.flex.items-center > div.flex.min-w-0:nth-` — 56x20 (needs 24x24) (in 4 cell(s)) — a "Projects" bg rgba(0, 0, 0, 0) class "hover:text-foreground"
- [target-size] `div.min-h-screen.bg-background > main.p-8 > div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type` — 16x16 (needs 24x24) (in 4 cell(s)) — button "About the Realism and Lighting slider" bg rgba(0, 0, 0, 0) class "inline-flex h-4 w-4 items-center justify-center rounded-full border border-muted"
- [target-size] `div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type(1) > div.flex.flex-wrap:nth-of-type(2) > di` — 7x16 (needs 24x24) (in 4 cell(s)) — button "Remove Archival Molding lock" bg rgba(0, 0, 0, 0) class "ml-0.5 text-muted-foreground hover:text-foreground"
- [target-size] `div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type(1) > div.flex.flex-wrap:nth-of-type(2) > di` — 7x16 (needs 24x24) (in 4 cell(s)) — button "Remove Hardwood Floors lock" bg rgba(0, 0, 0, 0) class "ml-0.5 text-muted-foreground hover:text-foreground"
- [target-size] `div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type(1) > div.flex.flex-wrap:nth-of-type(2) > di` — 7x16 (needs 24x24) (in 4 cell(s)) — button "Remove Exposed Brick lock" bg rgba(0, 0, 0, 0) class "ml-0.5 text-muted-foreground hover:text-foreground"
- [target-size] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div.flex.h-screen:nth-of-type(2) > a.sr-only.focus:n` — 1x1 (needs 24x24) (in 4 cell(s)) — a "Skip to main content" bg rgba(0, 0, 0, 0) class "sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:"
- [target-size] `main.p-8 > div.grid.gap-8:nth-of-type(3) > div.space-y-3.rounded-lg:nth-of-type(1) > div.flex.items-center:nth` — 16x16 (needs 24x24) (in 4 cell(s)) — button "Drag to reorder room" bg rgba(0, 0, 0, 0) class "cursor-grab text-muted-foreground hover:text-foreground touch-none"
- [target-size] `main.p-8 > div.grid.gap-8:nth-of-type(3) > div.space-y-3.rounded-lg:nth-of-type(1) > div.flex.items-center:nth` — 16x16 (needs 24x24) (in 4 cell(s)) — input "Select Rehearsal Room" bg rgba(0, 0, 0, 0) class "h-4 w-4 rounded border-input text-primary accent-primary"
- [target-size] `main.p-8 > div.grid.gap-8:nth-of-type(3) > div.space-y-3.rounded-lg:nth-of-type(2) > div.flex.items-center:nth` — 16x16 (needs 24x24) (in 4 cell(s)) — button "Drag to reorder room" bg rgba(0, 0, 0, 0) class "cursor-grab text-muted-foreground hover:text-foreground touch-none"
- [target-size] `main.p-8 > div.grid.gap-8:nth-of-type(3) > div.space-y-3.rounded-lg:nth-of-type(2) > div.flex.items-center:nth` — 16x16 (needs 24x24) (in 4 cell(s)) — input "Select Lookbook Suite" bg rgba(0, 0, 0, 0) class "h-4 w-4 rounded border-input text-primary accent-primary"
- [target-size] `main.p-8 > div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type(1) > div.flex.flex-wrap:nth-of-t` — 53x22 (needs 24x24) (in 4 cell(s)) — button "+ Add" bg rgba(0, 0, 0, 0) class "inline-flex items-center gap-0.5 rounded-full border border-dashed border-border"
- [target-size] `main.p-8 > div.sticky.top-0:nth-of-type(2) > div.grid.grid-cols-1:nth-of-type(1) > div.flex.flex-wrap:nth-of-t` — 96x2 (needs 24x24) (in 4 cell(s)) — input "Realism and lighting slider" bg rgba(0, 0, 0, 0) class "atelier-slider w-24"

### room studio / edit-room — 31 unique P1 findings
- [color-contrast] `[".h-96 > .font-medium.text-sm"]` — 2 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 4.38 (foreground color: #79716b, background color: #f5f5f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".h-96 > .font-medium.text-sm"]` — 7 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 4.38 (foreground color: #79716b, background color: #f5f5f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".max-w-\\[16rem\\]"]` — 7 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".mt-6"]` — 3 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".mt-6"]` — 7 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".rounded-full"]` — 3 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.77 (foreground color: #181716, background color: #8f4d20, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".rounded-full"]` — 7 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.77 (foreground color: #181716, background color: #8f4d20, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".sm\\:inline"]` — 7 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".text-stone-400.text-xs"]` — 1 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.21 (foreground color: #a6a09b, background color: #eeedec, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".text-stone-400.text-xs"]` — 2 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.36 (foreground color: #a6a09b, background color: #f5f5f4, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".text-stone-400.text-xs"]` — 3 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.21 (foreground color: #a6a09b, background color: #eeedec, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".text-stone-400.text-xs"]` — 7 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.36 (foreground color: #a6a09b, background color: #f5f5f4, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `["a[href$=\"projects\"]"]` — 7 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 10.5pt (14px), font weight: normal). E
- [rendered-contrast] `#main-content > div.min-h-screen.bg-background > header.shrink-0.bg-background > div.flex.items-center > div.f` — 3.58:1 (needs 4.5:1, 14px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "· Rehearsal Client"
- [rendered-contrast] `#main-content > div.min-h-screen.bg-background > main.p-8 > div.flex.min-h-0 > p.mt-6.text-sm` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Upload a room photo first to enable AI staging and copy."
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(1) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Upload Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(1) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "101 Upload Lane"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(2) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Editor Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(2) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "202 Editor Court"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(3) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Concept Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(3) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "404 Concept Crescent"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(5) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Signoff Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(5) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "505 Signature Way"
- [rendered-contrast] `div.min-h-screen.bg-background > header.shrink-0.bg-background > div.flex.items-center > div.flex.min-w-0:nth-` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Projects"
- [rendered-contrast] `div.min-h-screen.bg-background > header.shrink-0.bg-background > div.flex.items-center > div.flex.min-w-0:nth-` — 3.58:1 (needs 4.5:1, 14px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "303 Rehearsal Road"
- [rendered-contrast] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div.flex.h-screen:nth-of-type(2) > aside.no-print.fi` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Settings"
- [rendered-contrast] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div.flex.h-screen:nth-of-type(2) > aside.no-print.fi` — 3.58:1 (needs 4.5:1, 12px/600) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Projects"
- [rendered-contrast] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div:nth-of-type(4)` — 1.05:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "agentation: disconnected"
- [target-size] `div.min-h-screen.bg-background > header.shrink-0.bg-background > div.flex.items-center > div.flex.min-w-0:nth-` — 56x20 (needs 24x24) (in 4 cell(s)) — a "Projects" bg rgba(0, 0, 0, 0) class "hover:text-foreground"
- [target-size] `div.min-h-screen.bg-background > header.shrink-0.bg-background > div.flex.items-center > div.flex.min-w-0:nth-` — 132x20 (needs 24x24) (in 2 cell(s)) — button "303 Rehearsal Road" bg rgba(0, 0, 0, 0) class "max-w-[16rem] truncate hover:text-foreground hover:underline"
- [target-size] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div.flex.h-screen:nth-of-type(2) > a.sr-only.focus:n` — 1x1 (needs 24x24) (in 4 cell(s)) — a "Skip to main content" bg rgba(0, 0, 0, 0) class "sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:"

### lookbook editor — 201 unique P1 findings
- [color-contrast] `["#challenge-e2elookbookroom00000000000room"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["#challenge-e2elookbookroom00000000000room"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["#challenge-e2erehearsalroom0000000000room"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["#challenge-e2erehearsalroom0000000000room"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["#psychology-e2elookbookroom00000000000room"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["#psychology-e2elookbookroom00000000000room"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["#psychology-e2erehearsalroom0000000000room"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["#psychology-e2erehearsalroom0000000000room"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["#recommendation-e2elookbookroom00000000000room"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["#recommendation-e2elookbookroom00000000000room"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["#recommendation-e2erehearsalroom0000000000room"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["#recommendation-e2erehearsalroom0000000000room"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".border-primary"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.25 (foreground color: #ffffff, background color: #e5e5e5, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".border-primary"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.25 (foreground color: #ffffff, background color: #e5e5e5, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".gap-2:nth-child(1) > .min-w-0.px-2[type=\"text\"]"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".gap-2:nth-child(1) > .min-w-0.px-2[type=\"text\"]"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".gap-2:nth-child(1) > select"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".gap-2:nth-child(1) > select"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".gap-2:nth-child(2) > .min-w-0.px-2[type=\"text\"]"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".gap-2:nth-child(2) > .min-w-0.px-2[type=\"text\"]"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".gap-2:nth-child(2) > select"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".gap-2:nth-child(2) > select"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".max-w-2xl.space-y-8.avoid-break > .prose.prose-stone.mx-auto > .leading-relaxed.whitespace-pre-line.text-lg` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 13.5pt (18px), font weight: normal). E
- [color-contrast] `[".max-w-2xl.space-y-8.avoid-break > .prose.prose-stone.mx-auto > .leading-relaxed.whitespace-pre-line.text-lg` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 13.5pt (18px), font weight: normal). E
- [color-contrast] `[".max-w-2xl.space-y-8.avoid-break > .space-y-4:nth-child(1) > .text-4xl"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 27.0pt (36px), font weight: bold). Exp
- [color-contrast] `[".max-w-2xl.space-y-8.avoid-break > .space-y-4:nth-child(1) > .text-4xl"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 27.0pt (36px), font weight: bold). Exp
- [color-contrast] `[".max-w-3xl > .prose.prose-stone.mx-auto > .leading-relaxed.whitespace-pre-line.text-lg"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 13.5pt (18px), font weight: normal). E
- [color-contrast] `[".max-w-3xl > .prose.prose-stone.mx-auto > .leading-relaxed.whitespace-pre-line.text-lg"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 13.5pt (18px), font weight: normal). E
- [color-contrast] `[".max-w-3xl > .pt-12 > .tracking-widest.font-cinzel.text-muted-foreground"]` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".max-w-3xl > .pt-12 > .tracking-widest.font-cinzel.text-muted-foreground"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".max-w-3xl > .space-y-4 > .text-4xl"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 27.0pt (36px), font weight: bold). Exp
- [color-contrast] `[".max-w-3xl > .space-y-4 > .text-4xl"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 27.0pt (36px), font weight: bold). Exp
- [color-contrast] `[".max-w-3xl > .space-y-4 > .tracking-\\[0\\.3em\\].uppercase.font-cinzel"]` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".max-w-3xl > .space-y-4 > .tracking-\\[0\\.3em\\].uppercase.font-cinzel"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".mb-6.no-print.justify-between > .hover\\:bg-stone-100.transition-colors.text-stone-700"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.92 (foreground color: #44403b, background color: #0a0a0a, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".mb-6.no-print.justify-between > .hover\\:bg-stone-100.transition-colors.text-stone-700"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.92 (foreground color: #44403b, background color: #0a0a0a, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".mb-6.no-print.justify-between > div > h1"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.3 (foreground color: #292524, background color: #0a0a0a, font size: 18.0pt (24px), font weight: bold). Expe
- [color-contrast] `[".mb-6.no-print.justify-between > div > h1"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.3 (foreground color: #292524, background color: #0a0a0a, font size: 18.0pt (24px), font weight: bold). Expe
- [color-contrast] `[".ml-2"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.25 (foreground color: #e5e5e5, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".ml-2"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.25 (foreground color: #e5e5e5, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".mt-0\\.5"]` — 13 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".mt-0\\.5"]` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".mt-0\\.5"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".mt-0\\.5"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".p-12.lookbook-page.min-h-screen:nth-child(2) > footer > .items-start.py-4.px-0 > .space-y-0\\.5:nth-child(1` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-12.lookbook-page.min-h-screen:nth-child(2) > footer > .items-start.py-4.px-0 > .space-y-0\\.5:nth-child(1` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-12.lookbook-page.min-h-screen:nth-child(2) > footer > .items-start.py-4.px-0 > .space-y-0\\.5:nth-child(1` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.25 (foreground color: #e5e5e5, background color: #ffffff, font size: 12.0pt (16px), font weight: normal). E
- [color-contrast] `[".p-12.lookbook-page.min-h-screen:nth-child(2) > footer > .items-start.py-4.px-0 > .text-right.space-y-0\\.5 ` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-12.lookbook-page.min-h-screen:nth-child(2) > footer > .items-start.py-4.px-0 > .text-right.space-y-0\\.5 ` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".p-12.lookbook-page.min-h-screen:nth-child(2) > footer > .items-start.py-4.px-0 > .text-right.space-y-0\\.5 ` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".paper-preview:nth-child(1) > .p-12.lookbook-page.min-h-screen:nth-child(1) > .flex-1.flex-col.justify-cente` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".paper-preview:nth-child(1) > .p-12.lookbook-page.min-h-screen:nth-child(1) > .flex-1.flex-col.justify-cente` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".paper-preview:nth-child(1) > .p-12.lookbook-page.min-h-screen:nth-child(1) > .flex-1.flex-col.justify-cente` — 13 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".paper-preview:nth-child(1) > .p-12.lookbook-page.min-h-screen:nth-child(1) > .flex-1.flex-col.justify-cente` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".paper-preview:nth-child(1) > .p-12.lookbook-page.min-h-screen:nth-child(1) > .flex-1.flex-col.justify-cente` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".paper-preview:nth-child(1) > .p-12.lookbook-page.min-h-screen:nth-child(1) > .flex-1.flex-col.justify-cente` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".paper-preview:nth-child(1) > .p-12.lookbook-page.min-h-screen:nth-child(1) > footer > .items-start.py-4.px-` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".paper-preview:nth-child(1) > .p-12.lookbook-page.min-h-screen:nth-child(1) > footer > .items-start.py-4.px-` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".paper-preview:nth-child(1) > .p-12.lookbook-page.min-h-screen:nth-child(1) > footer > .items-start.py-4.px-` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.25 (foreground color: #e5e5e5, background color: #ffffff, font size: 12.0pt (16px), font weight: normal). E
- [color-contrast] `[".paper-preview:nth-child(1) > .p-12.lookbook-page.min-h-screen:nth-child(1) > footer > .items-start.py-4.px-` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".paper-preview:nth-child(1) > .p-12.lookbook-page.min-h-screen:nth-child(1) > footer > .items-start.py-4.px-` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".paper-preview:nth-child(1) > .p-12.lookbook-page.min-h-screen:nth-child(1) > footer > .items-start.py-4.px-` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".paper-preview:nth-child(6) > .p-12.lookbook-page.min-h-screen > .flex-1.flex-col.justify-center > .max-w-2x` — 13 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".paper-preview:nth-child(6) > .p-12.lookbook-page.min-h-screen > .flex-1.flex-col.justify-center > .max-w-2x` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".paper-preview:nth-child(6) > .p-12.lookbook-page.min-h-screen > .flex-1.flex-col.justify-center > .max-w-2x` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".paper-preview:nth-child(6) > .p-12.lookbook-page.min-h-screen > .flex-1.flex-col.justify-center > .max-w-2x` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".paper-preview:nth-child(6) > .p-12.lookbook-page.min-h-screen > footer > .items-start.py-4.px-0 > .space-y-` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".paper-preview:nth-child(6) > .p-12.lookbook-page.min-h-screen > footer > .items-start.py-4.px-0 > .space-y-` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".paper-preview:nth-child(6) > .p-12.lookbook-page.min-h-screen > footer > .items-start.py-4.px-0 > .space-y-` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.25 (foreground color: #e5e5e5, background color: #ffffff, font size: 12.0pt (16px), font weight: normal). E
- [color-contrast] `[".paper-preview:nth-child(6) > .p-12.lookbook-page.min-h-screen > footer > .items-start.py-4.px-0 > .text-rig` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".paper-preview:nth-child(6) > .p-12.lookbook-page.min-h-screen > footer > .items-start.py-4.px-0 > .text-rig` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".paper-preview:nth-child(6) > .p-12.lookbook-page.min-h-screen > footer > .items-start.py-4.px-0 > .text-rig` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".pt-12.border-border.border-t > .tracking-widest.font-cinzel.text-muted-foreground"]` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".pt-12.border-border.border-t > .tracking-widest.font-cinzel.text-muted-foreground"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".pt-8.space-y-2 > .font-jakarta.text-muted-foreground.text-sm"]` — 13 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".pt-8.space-y-2 > .font-jakarta.text-muted-foreground.text-sm"]` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".pt-8.space-y-2 > .font-jakarta.text-muted-foreground.text-sm"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".pt-8.space-y-2 > .font-jakarta.text-muted-foreground.text-sm"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".pt-8.space-y-2 > .text-xl.font-playfair.text-foreground"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 15.0pt (20px), font weight: normal). E
- [color-contrast] `[".pt-8.space-y-2 > .text-xl.font-playfair.text-foreground"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 15.0pt (20px), font weight: normal). E
- [color-contrast] `[".py-1.rounded-full.border-border:nth-child(1)"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".py-1.rounded-full.border-border:nth-child(2)"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".py-6"]` — 13 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a6a09b, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".py-6"]` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a6a09b, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".py-6"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a6a09b, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".py-6"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a6a09b, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".py-8.text-center.font-jakarta"]` — 13 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".py-8.text-center.font-jakarta"]` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".py-8.text-center.font-jakarta"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".py-8.text-center.font-jakarta"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".relative.aspect-\\[4\\/3\\].overflow-hidden:nth-child(1) > .h-full.justify-center.items-center > .text-ston` — 13 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.36 (foreground color: #a6a09b, background color: #f5f5f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".relative.aspect-\\[4\\/3\\].overflow-hidden:nth-child(1) > .h-full.justify-center.items-center > .text-ston` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.36 (foreground color: #a6a09b, background color: #f5f5f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".relative.aspect-\\[4\\/3\\].overflow-hidden:nth-child(1) > .h-full.justify-center.items-center > .text-ston` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.36 (foreground color: #a6a09b, background color: #f5f5f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".relative.aspect-\\[4\\/3\\].overflow-hidden:nth-child(1) > .h-full.justify-center.items-center > .text-ston` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.36 (foreground color: #a6a09b, background color: #f5f5f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".relative.aspect-\\[4\\/3\\].overflow-hidden:nth-child(2) > .h-full.justify-center.items-center > .text-ston` — 13 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.36 (foreground color: #a6a09b, background color: #f5f5f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".relative.aspect-\\[4\\/3\\].overflow-hidden:nth-child(2) > .h-full.justify-center.items-center > .text-ston` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.36 (foreground color: #a6a09b, background color: #f5f5f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".relative.aspect-\\[4\\/3\\].overflow-hidden:nth-child(2) > .h-full.justify-center.items-center > .text-ston` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.36 (foreground color: #a6a09b, background color: #f5f5f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".relative.aspect-\\[4\\/3\\].overflow-hidden:nth-child(2) > .h-full.justify-center.items-center > .text-ston` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.36 (foreground color: #a6a09b, background color: #f5f5f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".space-y-1 > .font-jakarta.text-muted-foreground"]` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 12.0pt (16px), font weight: normal). E
- [color-contrast] `[".space-y-1 > .font-jakarta.text-muted-foreground"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 12.0pt (16px), font weight: normal). E
- [color-contrast] `[".space-y-1 > .text-xl.font-playfair.text-foreground"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 15.0pt (20px), font weight: normal). E
- [color-contrast] `[".text-2xl.font-playfair.text-foreground"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 18.0pt (24px), font weight: normal). E
- [color-contrast] `[".text-2xl.font-playfair.text-foreground"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 18.0pt (24px), font weight: normal). E
- [color-contrast] `[".text-5xl"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 36.0pt (48px), font weight: bold). Exp
- [color-contrast] `[".text-5xl"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.04 (foreground color: #fafafa, background color: #ffffff, font size: 36.0pt (48px), font weight: bold). Exp
- [color-contrast] `[".text-lg.font-jakarta.text-muted-foreground"]` — 13 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 13.5pt (18px), font weight: normal). E
- [color-contrast] `[".text-lg.font-jakarta.text-muted-foreground"]` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.75 (foreground color: #8c827a, background color: #ffffff, font size: 13.5pt (18px), font weight: normal). E
- [color-contrast] `[".text-lg.font-jakarta.text-muted-foreground"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 13.5pt (18px), font weight: normal). E
- [color-contrast] `[".text-lg.font-jakarta.text-muted-foreground"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a1a1a1, background color: #ffffff, font size: 13.5pt (18px), font weight: normal). E
- [color-contrast] `[".text-stone-500"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 4.13 (foreground color: #79716b, background color: #0a0a0a, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".text-stone-500"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 4.13 (foreground color: #79716b, background color: #0a0a0a, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".tracking-widest.uppercase.font-cinzel"]` — 13 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.59 (foreground color: #8c827a, background color: #fafaf9, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".tracking-widest.uppercase.font-cinzel"]` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.59 (foreground color: #8c827a, background color: #fafaf9, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".tracking-widest.uppercase.font-cinzel"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.47 (foreground color: #a1a1a1, background color: #fafaf9, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `[".tracking-widest.uppercase.font-cinzel"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.47 (foreground color: #a1a1a1, background color: #fafaf9, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `["fieldset > .text-stone-400.text-sm"]` — 13 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a6a09b, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["fieldset > .text-stone-400.text-sm"]` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a6a09b, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["fieldset > .text-stone-400.text-sm"]` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a6a09b, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["fieldset > .text-stone-400.text-sm"]` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.58 (foreground color: #a6a09b, background color: #ffffff, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["section:nth-child(5) > .lookbook-page.min-h-screen.bg-stone-50 > footer > .items-start.py-4.px-0 > .space-y-` — 13 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.59 (foreground color: #8c827a, background color: #fafaf9, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `["section:nth-child(5) > .lookbook-page.min-h-screen.bg-stone-50 > footer > .items-start.py-4.px-0 > .space-y-` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.59 (foreground color: #8c827a, background color: #fafaf9, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `["section:nth-child(5) > .lookbook-page.min-h-screen.bg-stone-50 > footer > .items-start.py-4.px-0 > .space-y-` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.47 (foreground color: #a1a1a1, background color: #fafaf9, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `["section:nth-child(5) > .lookbook-page.min-h-screen.bg-stone-50 > footer > .items-start.py-4.px-0 > .space-y-` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.47 (foreground color: #a1a1a1, background color: #fafaf9, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `["section:nth-child(5) > .lookbook-page.min-h-screen.bg-stone-50 > footer > .items-start.py-4.px-0 > .space-y-` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.2 (foreground color: #e5e5e5, background color: #fafaf9, font size: 12.0pt (16px), font weight: normal). Ex
- [color-contrast] `["section:nth-child(5) > .lookbook-page.min-h-screen.bg-stone-50 > footer > .items-start.py-4.px-0 > .space-y-` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.2 (foreground color: #e5e5e5, background color: #fafaf9, font size: 12.0pt (16px), font weight: normal). Ex
- [color-contrast] `["section:nth-child(5) > .lookbook-page.min-h-screen.bg-stone-50 > footer > .items-start.py-4.px-0 > .text-rig` — 13 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.59 (foreground color: #8c827a, background color: #fafaf9, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `["section:nth-child(5) > .lookbook-page.min-h-screen.bg-stone-50 > footer > .items-start.py-4.px-0 > .text-rig` — 24 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.59 (foreground color: #8c827a, background color: #fafaf9, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `["section:nth-child(5) > .lookbook-page.min-h-screen.bg-stone-50 > footer > .items-start.py-4.px-0 > .text-rig` — 36 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.47 (foreground color: #a1a1a1, background color: #fafaf9, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `["section:nth-child(5) > .lookbook-page.min-h-screen.bg-stone-50 > footer > .items-start.py-4.px-0 > .text-rig` — 56 node(s) (in 1 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.47 (foreground color: #a1a1a1, background color: #fafaf9, font size: 9.0pt (12px), font weight: normal). Ex
- [rendered-contrast] `#lookbook-swatches > div.rounded-lg.border > div.mb-4.flex > button.flex.items-center` — 1.05:1 (needs 4.5:1, 14px/500) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "Add Swatch"
- [rendered-contrast] `#lookbook-swatches > div.rounded-lg.border > div.mb-4.flex > button.flex.items-center` — 1:1 (needs 4.5:1, 14px/500) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 255, 255) — "Add Swatch"
- [rendered-contrast] `#lookbook-swatches > div.rounded-lg.border > div.mb-4.flex > div > p.font-jakarta.text-sm` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Finish and palette references for the lookbook"
- [rendered-contrast] `#main-content > div.mx-auto.max-w-4xl > div:nth-of-type(2) > div.no-print.sticky:nth-of-type(1) > div.inline-f` — 1.05:1 (needs 4.5:1, 14px/500) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "Edit"
- [rendered-contrast] `#main-content > div.mx-auto.max-w-4xl > div:nth-of-type(2) > div.no-print.sticky:nth-of-type(1) > div.inline-f` — 1:1 (needs 4.5:1, 14px/500) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 255, 255) — "Edit"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(1) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Upload Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(1) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "101 Upload Lane"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(2) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Editor Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(2) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "202 Editor Court"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(3) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Concept Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(3) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "404 Concept Crescent"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(4) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Rehearsal Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(4) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "303 Rehearsal Road"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(5) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Signoff Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(5) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "505 Signature Way"
- [rendered-contrast] `div.lookbook-page.min-h-screen > div.flex-1.flex > div.max-w-2xl.text-center > div.pt-8.space-y-4:nth-of-type(` — 3.58:1 (needs 4.5:1, 16px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "E2E Harness"
- [rendered-contrast] `div.paper-preview:nth-of-type(1) > div.lookbook-page.min-h-screen:nth-of-type(1) > div.flex-1.flex > div.max-w` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "STAGING LOOKBOOK"
- [rendered-contrast] `div.paper-preview:nth-of-type(1) > div.lookbook-page.min-h-screen:nth-of-type(1) > div.flex-1.flex > div.max-w` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Target Buyer Profile"
- [rendered-contrast] `div.paper-preview:nth-of-type(1) > div.lookbook-page.min-h-screen:nth-of-type(1) > div.flex-1.flex > div.max-w` — 3.58:1 (needs 4.5:1, 18px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Prepared for Rehearsal Client"
- [rendered-contrast] `div.paper-preview:nth-of-type(1) > div.lookbook-page.min-h-screen:nth-of-type(1) > div.flex-1.flex > div.max-w` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Circle G Designs — E2E"
- [rendered-contrast] `div.paper-preview:nth-of-type(1) > div.lookbook-page.min-h-screen:nth-of-type(1) > footer.proposal-footer.prin` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "AI-Powered Home Staging"
- [rendered-contrast] `div.paper-preview:nth-of-type(1) > div.lookbook-page.min-h-screen:nth-of-type(1) > footer.proposal-footer.prin` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "All renders retain AI watermark"
- [rendered-contrast] `div.paper-preview:nth-of-type(1) > div.lookbook-page.min-h-screen:nth-of-type(2) > div.flex-1.flex > div.max-w` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Circle G Designs — E2E"
- [rendered-contrast] `div.paper-preview:nth-of-type(1) > div.lookbook-page.min-h-screen:nth-of-type(2) > div.flex-1.flex > div.max-w` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Our Staging Philosophy"
- [rendered-contrast] `div.paper-preview:nth-of-type(1) > div.lookbook-page.min-h-screen:nth-of-type(2) > footer.proposal-footer.prin` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "AI-Powered Home Staging"
- [rendered-contrast] `div.paper-preview:nth-of-type(1) > div.lookbook-page.min-h-screen:nth-of-type(2) > footer.proposal-footer.prin` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "All renders retain AI watermark"
- [rendered-contrast] `div.paper-preview:nth-of-type(3) > div.lookbook-page.min-h-screen > div.flex-1.flex > div.max-w-2xl.text-cente` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "STAGED PROPERTIES"
- [rendered-contrast] `div.paper-preview:nth-of-type(3) > div.lookbook-page.min-h-screen > div.flex-1.flex > div.max-w-2xl.text-cente` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Thank You"
- [rendered-contrast] `div.paper-preview:nth-of-type(3) > div.lookbook-page.min-h-screen > footer.proposal-footer.print:proposal-foot` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "AI-Powered Home Staging"
- [rendered-contrast] `div.paper-preview:nth-of-type(3) > div.lookbook-page.min-h-screen > footer.proposal-footer.print:proposal-foot` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "All renders retain AI watermark"
- [rendered-contrast] `div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(1) > div.mb-5.grid:nth-of-type(2) > div.r` — 1.05:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "Before"
- [rendered-contrast] `div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(1) > div.mb-5.grid:nth-of-type(2) > div.r` — 1:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 255, 255) — "Before"
- [rendered-contrast] `div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(1) > div.mb-5.grid:nth-of-type(2) > div.r` — 1.05:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "After"
- [rendered-contrast] `div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(1) > div.mb-5.grid:nth-of-type(2) > div.r` — 1:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 255, 255) — "After"
- [rendered-contrast] `div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(2) > div.mb-5.grid:nth-of-type(2) > div.r` — 1.05:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "Before"
- [rendered-contrast] `div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(2) > div.mb-5.grid:nth-of-type(2) > div.r` — 1:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 255, 255) — "Before"
- [rendered-contrast] `div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(2) > div.mb-5.grid:nth-of-type(2) > div.r` — 1.05:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "After"
- [rendered-contrast] `div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(2) > div.mb-5.grid:nth-of-type(2) > div.r` — 1:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 255, 255) — "After"
- [rendered-contrast] `div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(3) > div.lookbook-page.min-h-screen:nth-o` — 1.05:1 (needs 4.5:1, 14px/500) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "+ Add Item"
- [rendered-contrast] `div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(3) > div.lookbook-page.min-h-screen:nth-o` — 1:1 (needs 4.5:1, 14px/500) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 255, 255) — "+ Add Item"
- [rendered-contrast] `div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(3) > div.lookbook-page.min-h-screen:nth-o` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Vendor & SKU Reference"
- [rendered-contrast] `div:nth-of-type(2) > div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(1) > div.mb-4.flex:n` — 1.05:1 (needs 4.5:1, 14px/500) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "Generate copy"
- [rendered-contrast] `div:nth-of-type(2) > div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(1) > div.mb-4.flex:n` — 1:1 (needs 4.5:1, 14px/500) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 255, 255) — "Generate copy"
- [rendered-contrast] `div:nth-of-type(2) > div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(3) > div.lookbook-pa` — 3.58:1 (needs 4.5:1, 14px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "No procurement items yet."
- [rendered-contrast] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div.flex.h-screen:nth-of-type(2) > aside.no-print.fi` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Settings"
- [rendered-contrast] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div.flex.h-screen:nth-of-type(2) > aside.no-print.fi` — 3.58:1 (needs 4.5:1, 12px/600) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Projects"
- [rendered-contrast] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div:nth-of-type(4)` — 1.05:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "agentation: disconnected"
- [rendered-contrast] `section.rounded-lg.border:nth-of-type(3) > div.lookbook-page.min-h-screen:nth-of-type(2) > footer.proposal-foo` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "AI-Powered Home Staging"
- [rendered-contrast] `section.rounded-lg.border:nth-of-type(3) > div.lookbook-page.min-h-screen:nth-of-type(2) > footer.proposal-foo` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "All renders retain AI watermark"
- [target-size] `div.lookbook-page.min-h-screen > footer.proposal-footer.print:proposal-footer-print > div.flex.items-start:nth` — 37x16 (needs 24x24) (in 4 cell(s)) — button "Policy" bg rgba(0, 0, 0, 0) class "hover:underline underline-offset-2"
- [target-size] `div.lookbook-page.min-h-screen > footer.proposal-footer.print:proposal-footer-print > div.flex.items-start:nth` — 42x16 (needs 24x24) (in 4 cell(s)) — button "Privacy" bg rgba(0, 0, 0, 0) class "hover:underline underline-offset-2"
- [target-size] `div.lookbook-page.min-h-screen > footer.proposal-footer.print:proposal-footer-print > div.flex.items-start:nth` — 36x16 (needs 24x24) (in 4 cell(s)) — button "Terms" bg rgba(0, 0, 0, 0) class "hover:underline underline-offset-2"
- [target-size] `div.lookbook-page.min-h-screen:nth-of-type(1) > footer.proposal-footer.print:proposal-footer-print > div.flex.` — 37x16 (needs 24x24) (in 4 cell(s)) — button "Policy" bg rgba(0, 0, 0, 0) class "hover:underline underline-offset-2"
- [target-size] `div.lookbook-page.min-h-screen:nth-of-type(1) > footer.proposal-footer.print:proposal-footer-print > div.flex.` — 42x16 (needs 24x24) (in 4 cell(s)) — button "Privacy" bg rgba(0, 0, 0, 0) class "hover:underline underline-offset-2"
- [target-size] `div.lookbook-page.min-h-screen:nth-of-type(1) > footer.proposal-footer.print:proposal-footer-print > div.flex.` — 36x16 (needs 24x24) (in 4 cell(s)) — button "Terms" bg rgba(0, 0, 0, 0) class "hover:underline underline-offset-2"
- [target-size] `div.lookbook-page.min-h-screen:nth-of-type(2) > footer.proposal-footer.print:proposal-footer-print > div.flex.` — 37x16 (needs 24x24) (in 8 cell(s)) — button "Policy" bg rgba(0, 0, 0, 0) class "hover:underline underline-offset-2"
- [target-size] `div.lookbook-page.min-h-screen:nth-of-type(2) > footer.proposal-footer.print:proposal-footer-print > div.flex.` — 42x16 (needs 24x24) (in 8 cell(s)) — button "Privacy" bg rgba(0, 0, 0, 0) class "hover:underline underline-offset-2"
- [target-size] `div.lookbook-page.min-h-screen:nth-of-type(2) > footer.proposal-footer.print:proposal-footer-print > div.flex.` — 36x16 (needs 24x24) (in 8 cell(s)) — button "Terms" bg rgba(0, 0, 0, 0) class "hover:underline underline-offset-2"
- [target-size] `div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(3) > div.lookbook-page.min-h-screen:nth-o` — 115x20 (needs 24x24) (in 4 cell(s)) — button "Add the first item." bg rgba(0, 0, 0, 0) class "ml-2 text-primary hover:underline"
- [target-size] `div:nth-of-type(2) > div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(1) > div.space-y-4:n` — 308x20 (needs 24x24) (in 2 cell(s)) — label "Observed challenge · Rehearsal Room" bg rgba(0, 0, 0, 0) class "mb-1 block text-sm font-medium text-stone-700"
- [target-size] `div:nth-of-type(2) > div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(1) > div.space-y-4:n` — 814x20 (needs 24x24) (in 2 cell(s)) — label "Observed challenge · Rehearsal Room" bg rgba(0, 0, 0, 0) class "mb-1 block text-sm font-medium text-stone-700"
- [target-size] `div:nth-of-type(2) > div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(1) > div.space-y-4:n` — 308x20 (needs 24x24) (in 2 cell(s)) — label "Recommendation · Rehearsal Room" bg rgba(0, 0, 0, 0) class "mb-1 block text-sm font-medium text-stone-700"
- [target-size] `div:nth-of-type(2) > div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(1) > div.space-y-4:n` — 814x20 (needs 24x24) (in 2 cell(s)) — label "Recommendation · Rehearsal Room" bg rgba(0, 0, 0, 0) class "mb-1 block text-sm font-medium text-stone-700"
- [target-size] `div:nth-of-type(2) > div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(1) > div.space-y-4:n` — 308x20 (needs 24x24) (in 2 cell(s)) — label "Buyer psychology · Rehearsal Room" bg rgba(0, 0, 0, 0) class "mb-1 block text-sm font-medium text-stone-700"
- [target-size] `div:nth-of-type(2) > div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(1) > div.space-y-4:n` — 814x20 (needs 24x24) (in 2 cell(s)) — label "Buyer psychology · Rehearsal Room" bg rgba(0, 0, 0, 0) class "mb-1 block text-sm font-medium text-stone-700"
- [target-size] `div:nth-of-type(2) > div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(2) > div.space-y-4:n` — 308x20 (needs 24x24) (in 2 cell(s)) — label "Observed challenge · Lookbook Suite" bg rgba(0, 0, 0, 0) class "mb-1 block text-sm font-medium text-stone-700"
- [target-size] `div:nth-of-type(2) > div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(2) > div.space-y-4:n` — 814x20 (needs 24x24) (in 2 cell(s)) — label "Observed challenge · Lookbook Suite" bg rgba(0, 0, 0, 0) class "mb-1 block text-sm font-medium text-stone-700"
- [target-size] `div:nth-of-type(2) > div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(2) > div.space-y-4:n` — 308x20 (needs 24x24) (in 2 cell(s)) — label "Recommendation · Lookbook Suite" bg rgba(0, 0, 0, 0) class "mb-1 block text-sm font-medium text-stone-700"
- [target-size] `div:nth-of-type(2) > div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(2) > div.space-y-4:n` — 814x20 (needs 24x24) (in 2 cell(s)) — label "Recommendation · Lookbook Suite" bg rgba(0, 0, 0, 0) class "mb-1 block text-sm font-medium text-stone-700"
- [target-size] `div:nth-of-type(2) > div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(2) > div.space-y-4:n` — 308x20 (needs 24x24) (in 2 cell(s)) — label "Buyer psychology · Lookbook Suite" bg rgba(0, 0, 0, 0) class "mb-1 block text-sm font-medium text-stone-700"
- [target-size] `div:nth-of-type(2) > div.space-y-6:nth-of-type(2) > section.rounded-lg.border:nth-of-type(2) > div.space-y-4:n` — 814x20 (needs 24x24) (in 2 cell(s)) — label "Buyer psychology · Lookbook Suite" bg rgba(0, 0, 0, 0) class "mb-1 block text-sm font-medium text-stone-700"
- [target-size] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div.flex.h-screen:nth-of-type(2) > a.sr-only.focus:n` — 1x1 (needs 24x24) (in 4 cell(s)) — a "Skip to main content" bg rgba(0, 0, 0, 0) class "sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:"

### settings — 36 unique P1 findings
- [color-contrast] `["#logo"]` — 5 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `[".leading-relaxed"]` — 2 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 2.59 (foreground color: #57534d, background color: #0a0a0a, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["div:nth-child(2) > .mt-0\\.5"]` — 5 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `["div:nth-child(3) > .mt-0\\.5"]` — 5 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 9.0pt (12px), font weight: normal). Ex
- [color-contrast] `["h1"]` — 2 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 1.3 (foreground color: #292524, background color: #0a0a0a, font size: 22.5pt (30px), font weight: bold). Expe
- [color-contrast] `["label[for=\"logo\"] > .text-muted-foreground"]` — 5 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 10.5pt (14px), font weight: normal). E
- [color-contrast] `["label[for=\"psychologyPageContent\"] > .text-muted-foreground"]` — 5 node(s) (in 2 cell(s)) — Fix any of the following:
  Element has insufficient color contrast of 3.57 (foreground color: #8c827a, background color: #fff8f4, font size: 10.5pt (14px), font weight: normal). E
- [rendered-contrast] `#main-content > div.p-8 > form.max-w-md.space-y-8 > button.group/button.inline-flex` — 1.05:1 (needs 4.5:1, 14px/500) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "Save Settings"
- [rendered-contrast] `#main-content > div.p-8 > form.max-w-md.space-y-8 > fieldset.rounded-md.border:nth-of-type(2) > div:nth-of-typ` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Add a paragraph describing your ideal buyer and the emotiona"
- [rendered-contrast] `#main-content > div.p-8 > form.max-w-md.space-y-8 > fieldset.rounded-md.border:nth-of-type(2) > div:nth-of-typ` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Add your closing message to the buyer — this appears as the "
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(1) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Upload Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(1) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "101 Upload Lane"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(2) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Editor Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(2) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "202 Editor Court"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(3) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Concept Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(3) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "404 Concept Crescent"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(4) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Rehearsal Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(4) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "303 Rehearsal Road"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(5) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 14px/500) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Signoff Client"
- [rendered-contrast] `aside.no-print.fixed:nth-of-type(2) > nav.px-4.pb-4 > ul.space-y-1 > li:nth-of-type(5) > a.block.rounded-md > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "505 Signature Way"
- [rendered-contrast] `div.p-8 > form.max-w-md.space-y-8 > fieldset.rounded-md.border:nth-of-type(1) > div:nth-of-type(3) > label.blo` — 3.58:1 (needs 4.5:1, 14px/500) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "(optional)"
- [rendered-contrast] `div.p-8 > form.max-w-md.space-y-8 > fieldset.rounded-md.border:nth-of-type(2) > div:nth-of-type(1) > label.blo` — 3.58:1 (needs 4.5:1, 14px/500) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "(page 2)"
- [rendered-contrast] `div.p-8 > form.max-w-md.space-y-8 > fieldset.rounded-md.border:nth-of-type(3) > div.flex.items-center > div > ` — 3.58:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Switch between light and dark themes"
- [rendered-contrast] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div.flex.h-screen:nth-of-type(2) > aside.no-print.fi` — 3.58:1 (needs 4.5:1, 12px/600) (in 1 cell(s)) — fg rgb(140, 130, 122) on bg rgb(255, 248, 244) — "Projects"
- [rendered-contrast] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div:nth-of-type(4)` — 1.05:1 (needs 4.5:1, 12px/400) (in 2 cell(s)) — fg rgb(255, 255, 255) on bg rgb(255, 248, 244) — "agentation: disconnected"
- [target-size] `#main-content > div.p-8 > form.max-w-md.space-y-8 > fieldset.rounded-md.border:nth-of-type(1) > div:nth-of-typ` — 292x20 (needs 24x24) (in 2 cell(s)) — label "Firm Name" bg rgba(0, 0, 0, 0) class "block text-sm font-medium text-foreground"
- [target-size] `#main-content > div.p-8 > form.max-w-md.space-y-8 > fieldset.rounded-md.border:nth-of-type(1) > div:nth-of-typ` — 414x20 (needs 24x24) (in 2 cell(s)) — label "Firm Name" bg rgba(0, 0, 0, 0) class "block text-sm font-medium text-foreground"
- [target-size] `#main-content > div.p-8 > form.max-w-md.space-y-8 > fieldset.rounded-md.border:nth-of-type(1) > div:nth-of-typ` — 292x20 (needs 24x24) (in 2 cell(s)) — label "Owner Name" bg rgba(0, 0, 0, 0) class "block text-sm font-medium text-foreground"
- [target-size] `#main-content > div.p-8 > form.max-w-md.space-y-8 > fieldset.rounded-md.border:nth-of-type(1) > div:nth-of-typ` — 414x20 (needs 24x24) (in 2 cell(s)) — label "Owner Name" bg rgba(0, 0, 0, 0) class "block text-sm font-medium text-foreground"
- [target-size] `#main-content > div.p-8 > form.max-w-md.space-y-8 > fieldset.rounded-md.border:nth-of-type(1) > div:nth-of-typ` — 292x20 (needs 24x24) (in 2 cell(s)) — label "Firm Logo" bg rgba(0, 0, 0, 0) class "block text-sm font-medium text-foreground"
- [target-size] `#main-content > div.p-8 > form.max-w-md.space-y-8 > fieldset.rounded-md.border:nth-of-type(1) > div:nth-of-typ` — 414x20 (needs 24x24) (in 2 cell(s)) — label "Firm Logo" bg rgba(0, 0, 0, 0) class "block text-sm font-medium text-foreground"
- [target-size] `#main-content > div.p-8 > form.max-w-md.space-y-8 > fieldset.rounded-md.border:nth-of-type(2) > div:nth-of-typ` — 292x20 (needs 24x24) (in 2 cell(s)) — label "Philosophy Page" bg rgba(0, 0, 0, 0) class "block text-sm font-medium text-foreground"
- [target-size] `#main-content > div.p-8 > form.max-w-md.space-y-8 > fieldset.rounded-md.border:nth-of-type(2) > div:nth-of-typ` — 414x20 (needs 24x24) (in 2 cell(s)) — label "Philosophy Page" bg rgba(0, 0, 0, 0) class "block text-sm font-medium text-foreground"
- [target-size] `#main-content > div.p-8 > form.max-w-md.space-y-8 > fieldset.rounded-md.border:nth-of-type(2) > div:nth-of-typ` — 292x20 (needs 24x24) (in 2 cell(s)) — label "Closing Page" bg rgba(0, 0, 0, 0) class "block text-sm font-medium text-foreground"
- [target-size] `#main-content > div.p-8 > form.max-w-md.space-y-8 > fieldset.rounded-md.border:nth-of-type(2) > div:nth-of-typ` — 414x20 (needs 24x24) (in 2 cell(s)) — label "Closing Page" bg rgba(0, 0, 0, 0) class "block text-sm font-medium text-foreground"
- [target-size] `html.s-wYxq_variable.GNMova_variable > body.antialiased > div.flex.h-screen:nth-of-type(2) > a.sr-only.focus:n` — 1x1 (needs 24x24) (in 4 cell(s)) — a "Skip to main content" bg rgba(0, 0, 0, 0) class "sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:"

## Gate 7 — hardcoded hex colours in staging-studio src/components + src/app (count only)

- Files scanned: 162; total hex occurrences: **878**
- Classified: design-token 191, material-swatch exception 73, **other 614**
- Worst files by 'other' count:
  - `src/app/(dashboard)/projects/[id]/project-detail-view.tsx` — 74
  - `src/components/edit-room/EditRoomStudio.tsx` — 51
  - `src/components/canvas/use-inpaint-runs.ts` — 37
  - `src/components/edit-room/types.ts` — 33
  - `src/components/edit-room/MaskLayer.tsx` — 28
  - `src/app/api/inpaint/route.ts` — 25
  - `src/app/actions/room-batch.ts` — 16
  - `src/app/api/sign-project/route.ts` — 14

## Lens surface — gates 1–4 on the generative-ui-diagnostic-lens renderer

**Scope.** The three fixture cases the lens' own runner assembles — `case1_ashrae140`, `case2_ground_coupled`, `case3_humid_latent` (`generative-ui-diagnostic-lens/fixtures/case_requests.json` against `generative-ui-diagnostic-lens/fixtures/runs/*.json`) — assembled with `assembler.assemble` against `manifest.manifest_from_run(run)` and rendered by `generative-ui-diagnostic-lens/renderer.py` `render_spec()` (renderer.py:105), exactly as `run_poc.py` does (run_poc.py:252, run_poc.py:127). Measured by `xias-ui-gates/lens_gates.py` (Python standard library only, no browser engine, no network). Raw output: `results/lens-gates-1-4.json`.

**Adaptations (static HTML, no DOM, no layout, no browser engine in this slice).** The staging gates are re-implemented as static measurements over the rendered HTML:

- Gate 1 (accessibility, serious/critical): axe itself is **not** run on this surface (**UNMEASURED**). The static adaptation checks the rules the surface can decide deterministically: missing/empty accessible names on interactive elements, missing `lang`, missing `title`, duplicate ids, and images/SVG without a text alternative.
- Gate 2 (rendered contrast): WCAG 2.2 contrast ratios computed from the colours the renderer actually specifies — the class rules in the renderer's `<style>` block (renderer.py:112-118) and the SVG `fill`/`stroke` attributes. Large text = ≥24 px, or ≥18.66 px bold.
- Gate 3 (target size): interactive elements (link/button/input, or an element with an interactive role or a click handler) whose inline `width`/`height` or viewBox-derived size is under 24×24 px.
- Gate 4 (overflow at 280 px): fixed pixel widths / min-widths in inline styles or in the `<style>` block, and SVG `viewBox` widths above 280 px without a responsive wrapper (`max-width:100%`, `width:100%` or an overflow container). The *rendered* `scrollWidth` of the lens HTML was **not** measured (**UNMEASURED** — no browser engine is available in this slice); the finding below is the static viewBox-width offender, which is what the lens emits.

**Assumptions (explicit).** The renderer's `<style>` block sets no page background and no body colour, so the UA defaults are assumed: page background `#ffffff`, body text `#000000`. Every colour below is cited with the `renderer.py` line that declares it.

| Colour resolved | Source | On | Ratio | Requirement | Result |
|---|---|---|---|---|---|
| `#000000` (body text, no rule) | UA default (no colour rule in renderer.py:112-118) | `#ffffff` (UA default) | 21.00:1 | 4.5:1 | pass |
| `#333333` (`.axis-label` fill, 11 px/400) | renderer.py:118 | `#ffffff` | 12.63:1 | 4.5:1 | pass |
| `#a00` (`.nodata` colour) | renderer.py:114 | `#ffffff` | 7.75:1 | 4.5:1 | pass (rule present; no `.nodata` element in these three cases) |
| `#000000` on `#ffdddd` (`.out` badge) | renderer.py:115 | — | 16.64:1 | 4.5:1 | pass |

### Raw table — lens surface (counts per case; worst example per gate)

| Case | Components | G1 a11y | G2 contrast | G3 target | G4 overflow | Worst G2 | Worst G4 |
|---|---|---|---|---|---|---|---|
| case1_ashrae140 | TimeSeriesChart ×2, DiffTable, KPICard | 0 | 0 (30 text elements measured) | 0 (0 interactive elements) | 2 | — | `svg.chart[doc#12] role=img aria-label=zone1_air_temperature` — viewBox width 520 px > 280 px viewport, no responsive wrapper (renderer.py:93) |
| case2_ground_coupled | TimeSeriesChart, DiffTable | 0 | 0 (21 text elements measured) | 0 (0 interactive elements) | 1 | — | `svg.chart[doc#12] role=img aria-label=floor_boundary_temperature` — viewBox width 520 px > 280 px viewport, no responsive wrapper (renderer.py:93) |
| case3_humid_latent | TimeSeriesChart ×2, DiffTable | 0 | 0 (27 text elements measured) | 0 (0 interactive elements) | 2 | — | `svg.chart[doc#12] role=img aria-label=zone1_relative_humidity` — viewBox width 520 px > 280 px viewport, no responsive wrapper (renderer.py:93) |

Totals for the lens surface: G1 **0**, G2 **0**, G3 **0**, G4 **5** (one offender per chart SVG). Gates failed: **gate 4 only — 1 of 4**. Gates 1 and 3 have no findings at all, so they have no worst example; gate 2 has no worst example because no text element fell below its requirement (the lowest ratio measured is 12.63:1 for the 11 px axis labels, the only non-default colour in these three cases).

**Worst-example convention on this surface.** The lens HTML carries no element ids, so elements are identified by tag + class + document-order index + a short text/attribute excerpt (e.g. `svg.chart[doc#12] role=img aria-label=zone1_air_temperature`).

**Reconciliation with the on-record line.** The "Totals and gate application" section above records, from the #46 comment of 2026-11-13, that the lens half "fails 1 of gates 1–4 (gate 4)". This slice re-measured the same three fixture cases with a reproducible script: gates 1, 2 and 3 measure **0** findings and gate 4 measures **5** findings — the lens fails **1 of gates 1–4, gate 4**. The measurement **agrees** with the on-record line; there is no divergence to resolve, and the old line is annotated rather than overwritten. What this slice adds is the artifact the old line lacked: the script (`lens_gates.py`), the raw results (`results/lens-gates-1-4.json`) and this table.

**Phase 0 implication for the lens surface alone.** The issue's rule is that a surface failing ≥3 of gates 1–4 contributes one Proceed leg. The lens surface fails **1** of gates 1–4 (gate 4 only), so it contributes **no** Proceed leg; the lens half remains NOT ≥3, exactly as recorded. This says nothing about the whole spike: the recorded whole-spike verdict (PROCEED) rests on the staging-studio screens, and gates 5–6 remain open for both surfaces.

## Totals and gate application

- Total findings (gates 1–4 violation counts + gate-7 'other', per the slice definition): **1310**.
- P1-class findings appear on **all 6 screens** (axe serious/critical and rendered-contrast failures on every screen; target-size failures on every screen).
- Lens half (already on record, #46 comment 2026-11-13): fails 1 of gates 1–4 (gate 4), i.e. NOT ≥3. — re-measured in this slice's lens-surface section with a reproducible script (`lens_gates.py`, `results/lens-gates-1-4.json`): the measurement **agrees** (1 of 4, gate 4); the original line is kept, not overwritten.
- **Verdict: PROCEED** — the parent gate's first condition is met (P1 findings on ≥2 staging-studio screens). The Kill condition (near-clean, <5 total, none P1) is nowhere near met. Gates 5 (keyboard) and 6 (verify-interactive) are **NOT measured** in this slice; the Proceed rests on gates 1–4 + 7 and does not need the unmeasured gates, but any future Kill judgement must be flagged as resting on 1–4+7 only.

## Claims

- [observed] All 24 screen×theme×viewport cells rendered the real staging-studio screens in the hermetic harness and were measured; counts and worst examples above come from `results/gates-1-4.json` (axe-core 4 + rendered-DOM measurement in Chromium); source: results/gates-1-4.json.
- [observed] Gate 4 (horizontal overflow at 390px) is 0 px on all six screens in both themes — unlike the lens renderer's fixture output, the real app does not overflow at 390px; source: results/gates-1-4.json.
- [observed] Gate 7 counts 878 hex occurrences, 614 classified 'other' (not design tokens, not material swatches) — from `results/gate7-hex-count.json`, a static count over src/components + src/app at the measured commit; source: results/gate7-hex-count.json.
- [observed] The dominant rendered failures are colour contrast (muted-foreground text at ~3.5:1 against a 4.5:1 requirement) and sub-24px targets, concentrated in project detail and the lookbook editor; source: results/gates-1-4.json.
- [inference] Because P1 findings appear on every screen, a Phase 1 gate wired into staging-studio's E2E would start red on day one; the gate-set wall-time (~72 s for the measurement pass, plus build/seed) is the ceiling it would add.
- [unsupported] Nothing here measures gates 5 (keyboard) or 6 (verify-interactive), real-user impact, or XIAS's effect on these numbers; no claim is made about them.
- [observed] On the lens surface (three fixture cases rendered by `generative-ui-diagnostic-lens/renderer.py`), gates 1–3 measure 0 findings and gate 4 measures 5 (one 520 px chart `viewBox` per chart SVG, above the 280 px viewport); source: results/lens-gates-1-4.json.
- [observed] The lens renderer emits no interactive elements (no link, button or input, and no interactive role) in these three cases, so gate 3 has nothing to measure on this surface; source: results/lens-gates-1-4.json.
- [observed] Every colour gate 2 resolves comes from the renderer's own `<style>` block or its SVG `fill`/`stroke` attributes, with the UA defaults `#ffffff` (page background) and `#000000` (body text) assumed where that block sets nothing; source: generative-ui-diagnostic-lens/renderer.py:112.
- [inference] Because the lens surface fails 1 of gates 1–4 it contributes no Proceed leg under the issue's rule (a surface needs ≥3 failures); the recorded whole-spike verdict rests on the staging-studio screens and is not changed by this section.

## Deliverables in this folder

- `REPORT.md` — this report.
- `gates.spec.ts` — the Playwright gate runner (copy into staging-studio `tests/e2e/specs/` to run; expects the harness's seeded fixtures, axe-core resolvable from the app's node_modules, results path via `XIAS_GATE_OUT`).
- `gate7-hex-count.mjs` — the gate-7 static counter (`node gate7-hex-count.mjs <staging-studio-root>`).
- `lens_gates.py` — the lens-surface gate runner (stdlib only): renders the lens' three fixture cases via `generative-ui-diagnostic-lens/renderer.py` and applies gates 1–4 to the static HTML (`python3 xias-ui-gates/lens_gates.py`).
- `test_lens_gates.py` — tests for the lens-surface gates (`python3 -m pytest xias-ui-gates/ -q`).
- `results/gates-1-4.json`, `results/gate7-hex-count.json` — the raw machine output behind every staging-studio number above.
- `results/lens-gates-1-4.json` — the raw machine output behind every lens-surface number above.
