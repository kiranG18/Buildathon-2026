# Design system

Extracted from `frontend/prototype/cadence-prototype.html`, which follows the BizLink B2B SaaS language. The prototype is the visual reference for every screen. Tokens live in `frontend/css/tokens.css`. Values below come from the prototype's CSS.

## Typography

- Family: Onest for UI text, IBM Plex Mono for ids, URLs, and code (12px). The prototype declares both and never loads them. Self-host both from `@fontsource/onest` and `@fontsource/ibm-plex-mono` into `frontend/fonts/` with `@font-face` rules, weights 450, 500, 550, 600.
- Body: 14px, line height 1.45, ink color, antialiased.
- Page title `.h1`: 28px, weight 550, letter spacing -0.025em, line height 1.15.
- Section title `.h2`: 22px, weight 550, letter spacing -0.02em.
- Card title `.h3`: 16px, weight 600.
- Small text `.small`: 12.5px. Breadcrumbs: 13px. Key-value rows: 13.5px. Pills and chips: 12.5px.
- Weights in use: 450 (nav, body emphasis), 500 (buttons, labels, table headers), 550 (active nav, pills, titles), 600 (brand, card titles).
- Secondary text uses `--ink2`. Tertiary text and timestamps use `--ink3`.

## Color

| Token | Value | Role |
| --- | --- | --- |
| `--paper` | #fff | Page and card background |
| `--cream` | #f6f7ee | Page header band |
| `--ink` | #1f201d | Primary text |
| `--ink2` | #5d5e58 | Secondary text |
| `--ink3` | #8f9088 | Tertiary text |
| `--line` | #e4e4e4 | Borders on cards, inputs, tables |
| `--line2` | #efefea | Row dividers, top bar border |
| `--mist` | #f5f5f5 | Hover and active fills, chips |
| `--live` and `--live-bg` | #20744c and #e6f2ea | Live state |
| `--pause` and `--pause-bg` | #9a5b00 and #fcf0d6 | Paused state |
| `--kill` and `--kill-bg` | #c23a2e and #fdeae7 | Kill switch, destructive |
| `--info` and `--info-bg` | #2c5a86 and #e7eff7 | Informational banners |
| `--warn` and `--warn-bg` | #8a6d00 and #f8f1cc | Warnings |
| `--c1` to `--c4`, `--cx` with `b` variants | see tokens.css | One color pair per campaign, plus one for cross-campaign items |

Primary buttons use #060705 with white text. One accent family per campaign identifies campaigns in feeds and tables. No other accent colors.

## Radius, spacing, layout

- Radius: 16px cards and empty states, 14px tiles, banners, toasts, 12px buttons, inputs, segmented controls, 10px small buttons and nav items, 8px chips and skeletons, 20px modals. Pills use 12px. Avatars are round.
- Spacing: page content padding 28px 32px. Header band padding 26px 32px 28px (slim: 22px 32px). Card padding 18px (tight: 14px). Grid gap 16px. Row gaps 4, 8, 12, 16, 24px. Board columns gap 20px.
- App shell: CSS grid, 256px sidebar and a flexible main area at 100vh. The main area scrolls, the shell does not.
- Sidebar: 26px 16px 16px padding, white, right border `--line`. Brand at 22px, weight 600. Nav items 10px 12px padding, 12px gap, 10px radius. Active and hover items use `--mist` and weight 550. Count badges sit at the right end.
- Top bar: sticky, 12px 32px padding, bottom border `--line2`, search field up to 480px, demo clock chip, notification button, and the red Stop all button.
- Page header: cream band with breadcrumbs, `.h1`, subtitle in `--ink2`, and page actions aligned right.
- Tabs: border-bottom row with 0 32px padding. Active tab has a 2px ink underline and weight 550.
- Target viewport: 1366 by 768. Breakpoints at 1100px and 900px.

## Components

- **Button:** 40px tall, 12px radius, 1px `--line` border, weight 500. Variants: primary (#060705), danger (`--kill`), warn (`--pause-bg`), ghost, small (32px, 10px radius, 13px text).
- **Input, select, textarea:** 40px, 12px radius, 1px `--line` border, 12px horizontal padding, labels above at 13px weight 550 with a 6px gap, hints at 12.5px in `--ink3`, errors at 12.5px in `--kill`.
- **Pill:** 24px tall, 12px radius, 12.5px weight 550, leading status dot. Live, Paused, Draft, Error variants use the state tokens.
- **Chip:** 24px tall, 8px radius, `--mist` fill, `--ink2` text. Outline variant (`.line`) is white with a `--line` border. Campaign chips use the campaign color pair.
- **Card:** white, 1px `--line` border, 16px radius. Card head holds a `.h3`, optional pill, and actions.
- **Tile (KPI):** white, 1px border, 14px radius, 14px 16px padding. Border darkens to ink on hover when clickable.
- **Table:** sticky header in `--ink2` weight 500, 12px 14px cell padding, `--line2` row dividers, vertical center alignment, scrolls inside its own container.
- **Segmented control:** 12px radius, 3px inner padding, 1px border.
- **Drawer:** 620px maximum, right side, white, 24px 26px padding, soft shadow, 0.18 second slide-in.
- **Modal:** 560px (large: 860px), 20px radius, 24px padding, shadow.
- **Toast:** ink background, white text, 14px radius, undo action on the right.
- **Kill bar:** full-width sticky red bar above the top bar with a Resume platform button.
- **Banner:** 14px radius, 12px 16px padding. Variants: paused (amber), bad (red), info (blue).
- **Empty state:** dashed 1px border, 16px radius, centered text, one action.
- **Skeleton:** 8px radius with a light shimmer. This is the only gradient in the product and it marks loading.
- **Stage bar:** funnel rows in a 110px, flexible, 90px grid.
- **Board (Prospects tab):** columns of at least 260px with 20px gaps, scrolling horizontally.
- **Avatar:** 32px circle with initials.

## State conventions

- Every state pairs color with a word and an icon. Live is green, Paused is amber, Draft is grey, Kill switch is a red banner across every screen.
- Every screen has a loading skeleton, a designed empty state, and an inline error state with Retry.
- Destructive and global actions ask for confirmation. Pause offers an undo toast.
- Every message shows `LIVE`, `SANDBOX`, or `REPLAY`. Seeded rows show a `DEMO` chip.
- Motion stays limited to the drawer slide, the skeleton shimmer, and a 2-second highlight on new feed rows. `prefers-reduced-motion` turns them off.

## Fixes to apply during the port

1. Load the fonts (see Typography).
2. Replace the top bar's translucent blur (`rgba(255,255,255,.94)` with `backdrop-filter`) with solid `--paper`.
3. Move inline `style=""` values from the render code into classes that use tokens.
4. Keep the hatched bar chart pattern and the skeleton shimmer. Both carry information.
