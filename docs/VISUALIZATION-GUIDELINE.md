# Opensens Office — Visualization Guideline

> Reference for all visual conventions, color systems, animation patterns, and component architecture used in the Agent Office frontend.

## 1. Color System

### Agent Status Colors

Every agent has a single visual status. This is the source of truth for ring color, badge color, and animation selection.

| Status | Hex | Usage |
|--------|-----|-------|
| `idle` | `#22c55e` (green) | Agent waiting for work |
| `thinking` | `#3b82f6` (blue) | LLM call in progress |
| `tool_calling` | `#f97316` (orange) | Executing a tool |
| `speaking` | `#a855f7` (purple) | Generating response |
| `spawning` | `#06b6d4` (cyan) | Sub-agent being created |
| `error` | `#ef4444` (red) | Failed or blocked |
| `offline` | `#6b7280` (gray) | Not connected |

**Rule:** Never hardcode these values. Always import from `lib/constants.ts → STATUS_COLORS`.

### Avatar Palette (12 deterministic colors)

```
#ef4444  #f97316  #f59e0b  #84cc16  #22c55e  #14b8a6
#06b6d4  #3b82f6  #6366f1  #8b5cf6  #a855f7  #ec4899
```

Selected via `hashString(agentId) % 12`. The same agent always gets the same color across sessions.

### Zone Colors

| Zone | Light | Dark |
|------|-------|------|
| Desk | `#f4f6f9` | `#1e293b` |
| Meeting | `#eef3fa` | `#1a2744` |
| Hot Desk | `#f1f3f7` | `#1e2433` |
| Lounge | `#f3f1f7` | `#231e33` |
| Corridor | `#e8ecf1` | `#0f172a` |
| Wall | `#8b9bb0` | `#475569` |

### Priority Colors (Paperclip Issues)

| Priority | Badge | Class |
|----------|-------|-------|
| Critical (P0) | Red | `bg-red-100 text-red-700` / `dark:bg-red-900/40 dark:text-red-300` |
| High (P1) | Orange | `bg-orange-100 text-orange-700` |
| Medium (P2) | Yellow (hidden in sidebar) | `bg-yellow-100 text-yellow-700` |
| Low (P3) | Gray | `bg-gray-100 text-gray-500` |

### Budget Gauge Colors

| Utilization | Color | Meaning |
|-------------|-------|---------|
| 0–60% | Green | Healthy |
| 60–85% | Yellow | Caution |
| 85%+ | Red | Near limit |

### DRVP Event Source Colors

| Source | Color | Usage |
|--------|-------|-------|
| OpenClaw | `#3b82f6` (blue) | Gateway events |
| DRVP | `#14b8a6` (teal) | Middleware pipeline events |

---

## 2. Agent Avatar

### 2D (SVG)

- **Generated deterministically** from `agentId` using a hash function
- **5 parameters:** face shape (round/square/oval), hair style (5 variants), eye style (3), skin color (6 tones), hair color (4 tones)
- **Ring radius:** 20px (24px when selected)
- **Ring stroke:** 3px, color = `STATUS_COLORS[status]`
- **Dashed ring:** `strokeDasharray="6 3"` for walking or placeholder agents

### Badges & Indicators

| Badge | Position | Trigger |
|-------|----------|---------|
| Sub-agent `S` | Top-right | `isSubAgent === true` |
| Error `!` | Top-right | `status === "error"` |
| Issue ID | Top-left | `issueId` present (linked blue box) |
| Tool name | Below avatar | `status === "tool_calling"` (orange pill) |
| Thinking dots | Above avatar | `status === "thinking"` (3 animated circles) |
| Speaking pulse | Above avatar | `status === "speaking"` (purple bubble) |

### 3D (R3F)

- **Body:** Capsule mesh (0.15 radius, 0.4 height)
- **Head:** Sphere (0.12 radius)
- **Opacity levels:**
  - Normal: 1.0
  - Sub-agent: 0.6
  - Unconfirmed: 0.35
  - Offline: 0.4
  - Placeholder: 0.25

---

## 3. Animation Reference

### Keyframes

| Name | Duration | Effect | Used By |
|------|----------|--------|---------|
| `agent-pulse` | 1–2s | Scale 1→1.08, opacity 0.5→1 | Thinking, tool calling, speaking rings |
| `agent-blink` | 0.8s | Opacity 1→0.35 | Error state ring |
| `agent-spawn` | 0.5s | Scale 0→1 (fill forwards) | New agent appearing |
| `agent-despawn` | — | Scale 1→0, opacity 1→0 | Agent removed |
| `thinking-dots` | 1.2s | Opacity 0.3→1→0.3 (staggered 40ms) | Thinking indicator |
| `connection-pulse` | 0.8s | Dash-offset 24→0 | Strong collaboration links |
| `dash-flow` | 1.5s | Dash-offset →−20 | Weak collaboration links |
| `hologram-progress` | 1.5s | TranslateX −100%→100% | Skill hologram progress bar |
| `chat-slide-up` | 200ms | TranslateY 100%→0 | Chat dock opening |
| `chat-slide-down` | 150ms | TranslateY 0→100% | Chat dock closing |

### Status-to-Animation Mapping

| Status | Animation | Ring Dash | Duration |
|--------|-----------|-----------|----------|
| `idle` | None | Solid | — |
| `thinking` | `agent-pulse` | Solid | 1.5s |
| `tool_calling` | `agent-pulse` | Dashed 6-3 | 2s |
| `speaking` | `agent-pulse` | Solid | 1s |
| `error` | `agent-blink` | Solid | 0.8s |
| `spawning` | `agent-spawn` | Solid | 0.5s |
| `offline` | None | Solid | — |

### Walk Animation (2D)

- Bob frequency: 8 Hz, amplitude: 2px
- Scale: ramp up (0.9→1.0) in first 10%, ramp down in last 10%
- Uses `requestAnimationFrame` loop

### Walk Animation (3D)

- Sway: ±0.08 radians at 8 Hz
- Bounce: 3cm amplitude
- Position lerp: 0.1 factor (smooth glide)

---

## 4. Floor Plan Layout

### Zone Architecture

```
 ┌────────────┬────────────┐
 │            │            │
 │   DESK     │  MEETING   │
 │  (4×3 grid)│  (circular)│
 │            │            │
 ├────────────┼────────────┤
 │            │            │
 │  HOT DESK  │  LOUNGE    │
 │  (4×3 grid)│  (sofas)   │
 │            │            │
 └────────────┴────────────┘
       CORRIDOR (cross-shaped)
```

### SVG Rendering Layers (bottom to top)

1. **Building shell** — outer rounded rect, 6px wall
2. **Corridor** — tile pattern fill (28×28px grid)
3. **Zone floors** — colored rectangles (zone-specific colors)
4. **Partition walls** — 4px architectural lines
5. **Door openings** — dashed arc swing indicators
6. **Furniture** — desks, chairs, sofas, plants, coffee cups
7. **Collaboration lines** — quadratic Bezier curves between agents
8. **Agent avatars** — positioned SVG groups (topmost layer)

### Desk Grid

- Adaptive columns: `max(4, min(availWidth / 100, agentCount))`
- Unit size: 140×110px (desk 100×60 + chair 30 + avatar radius 20)
- Spacing: 20px gap

### Meeting Layout

- Circular table at center, radius scales with agent count (60–100px)
- Seat radius: `60 + count × 8` (capped at 136px)
- Equal angular distribution

---

## 5. Collaboration Links

### Styling Rules

| Strength | Stroke | Dash | Shadow | Animation |
|----------|--------|------|--------|-----------|
| ≥ 0.5 (strong) | 3px | 12-6 | Glow drop-shadow | `connection-pulse` 0.8s |
| < 0.5 (weak) | 1.5px | 6-4 | Subtle | `dash-flow` 1.5s |

- Opacity: `max(0.2, strength)`
- Shape: Quadratic Bezier with offset control point
- Background: +2px blur at 3% opacity for glow

---

## 6. Charts & Data Visualization

### TokenLineChart (Recharts)

- **Type:** Line chart with time axis
- **Total line:** Blue solid, 2px stroke
- **Per-agent lines:** Dashed 4-2, colors from avatar palette
- **Y-axis format:** `1M`, `1k`, plain number
- **Time axis:** `HH:MM` format
- **Limit:** Top 5 agents by total tokens

### CostPieChart (Recharts)

- **Type:** Donut chart
- **Inner/outer radius:** 50/80px
- **Colors:** `generateAvatar3dColor(agentId)` for consistency
- **Center:** Total cost in `$XX.XX` format
- **Tooltip:** `AgentName: $value (XX%)`

### ActivityHeatmap (SVG)

- **Grid:** 10 rows (agents) × 24 columns (hours)
- **Cell:** 10×14px
- **Color scale (light):** `#f3f4f6` → `#16a34a` (white to green)
- **Color scale (dark):** `#1e293b` → `#22c55e` (dark to green)
- **Hover:** Tooltip with agent name, hour, event count

### NetworkGraph (SVG)

- **Layout:** Circular, top 20 agents by tool call count
- **Node size:** Linear map 8–24px based on tool count
- **Link width:** `strength × 3px`
- **Link opacity:** = `strength` value
- **Hover:** Highlights connected links, agent name tooltip

### BudgetGauge (SVG Arc)

- **Arc:** 270 degrees, starting at 135 degrees
- **Background:** `#e5e7eb` (light) / `#374151` (dark)
- **Fill:** Green → yellow → red based on percentage
- **Center text:** `XX%` in large bold font
- **Label:** Agent name below the arc

---

## 7. Panel Components

### EventTimeline

- **Unified stream:** Merges OpenClaw + DRVP events by timestamp
- **Source indicator:** Colored dot (blue = OpenClaw, teal = DRVP)
- **Auto-scroll:** Follows bottom, shows "new events" button when scrolled up
- **Detail extraction:** Rich payload details for 18+ event types (handoff direction, LLM model/cost, campaign step progress, browser domain, budget utilization)
- **Max display:** 80 events (circular buffer in store holds 500)

### PaperclipPanel

- **Stat pills:** Spend, pending approvals, open issues
- **Alert bar:** Campaign count (purple), approval queue (amber), boost status (cyan)
- **Budget gauges:** Per-agent arc gauges
- **Active issues list:** With priority badges (P0/P1/P3) and assignee name

### RequestCard

- **Collapsed:** Agent name, request ID (12 chars), last event type, elapsed time
- **Campaign bar:** Purple progress bar with step N/M, quality score badge
- **Approval badge:** Amber when awaiting CEO approval
- **Expanded:** RequestFlowTree showing linked Paperclip issues as a vertical tree

---

## 8. DRVP Event Icons

| Event | Icon | Detail Format |
|-------|------|---------------|
| `request.created` | `▶` | Request title |
| `request.completed` | `✓` | — |
| `request.failed` | `✕` | Error message |
| `agent.activated` | `⚡` | — |
| `agent.thinking` | `💭` | — |
| `agent.speaking` | `💬` | — |
| `handoff.started` | `↗` | `→ ToAgent` |
| `handoff.completed` | `↘` | `FromAgent → ToAgent` |
| `tool.call.started` | `🔧` | Tool name |
| `tool.call.completed` | `✓` | Tool name + "ok" |
| `tool.call.failed` | `✕` | Tool name + error |
| `llm.call.started` | `🧠` | — |
| `llm.call.completed` | `✓` | `model · IN→OUT tok · $cost` |
| `llm.call.boosted` | `⚡` | `BOOST · model · via provider · tok` |
| `budget.warning` | `💰` | `XX% used` or `$X.XX remaining` |
| `budget.exhausted` | `🚫` | Agent name |
| `campaign.step.started` | `▶` | `N/M title` |
| `campaign.step.completed` | `✓` | `N/M · Q:XX%` |
| `campaign.approval.required` | `⏸` | `"title" needs approval` |
| `campaign.approved` | `✅` | — |
| `browser.navigate` | `🌐` | Hostname |
| `browser.action` | `🖱` | Action name |
| `browser.blocked` | `🛡` | `domain blocked by allowlist` |
| `memory.read` | `📖` | Query text |
| `memory.write` | `📝` | Key name |

---

## 9. Theme System

All components support `light` and `dark` modes via the office store `theme` property.

### Rules

1. **Zone colors:** Use `ZONE_COLORS[zone]` (light) vs `ZONE_COLORS_DARK[zone]` (dark)
2. **Tailwind:** Prefix dark variants with `dark:` (e.g. `bg-gray-50 dark:bg-gray-800`)
3. **SVG fills:** Check `isDark` from store and select appropriate constant
4. **3D scene:** Background interpolates smoothly between light `#f8fafc` and dark `#0f172a`
5. **Charts:** Use theme-aware color scales (see ActivityHeatmap, BudgetGauge)

---

## 10. Component Composition Rules

### Memoization

- `AgentAvatar`: Memoized with custom `areEqual` comparing `id`, `status`, `name`, `currentTool`, `isSubAgent`, `speechBubble`
- `DeskUnit`: Memoized comparing all agent visual properties
- **Rule:** Memoize any component that re-renders on every store tick (60fps animation loop)

### SVG-in-React Patterns

- Use `<g transform={...}>` for positioning (not CSS transforms)
- Use `<foreignObject>` for HTML content inside SVG (speech bubbles, tooltips)
- Use `<defs>` for reusable patterns (tile grids, gradients)
- All coordinates in SVG user units (not pixels)

### Store Access

- Use Zustand selectors for fine-grained subscriptions: `useOfficeStore((s) => s.agents)`
- Never subscribe to the entire store object
- DRVP data: `useDrvpStore` (events, active requests, campaign progress)
- Paperclip data: `usePaperclipStore` (dashboard, agents, issues, costs)

### File Size Limit

- **500 lines max per file** — split when longer
- Components: PascalCase filenames
- Hooks: `useCamelCase` filenames
- Constants: kebab-case or camelCase

---

## 11. Adding New Visualizations

### Checklist

1. Define colors in `lib/constants.ts` (never hardcode hex values)
2. Support both light and dark themes
3. Use Recharts for data charts, raw SVG for custom graphics
4. Add i18n keys for all user-visible labels
5. Memoize if the component renders inside the animation loop
6. Test with `@testing-library/react` for key interactions
7. Keep under 500 lines; split rendering helpers into sub-components

### Adding a New DRVP Event Type

1. Add to `DRVPEventType` enum in `core/oas_core/protocols/drvp.py`
2. Add to `DRVP_EVENT_TYPES` array in `office/src/drvp/drvp-types.ts`
3. Add icon in `EventTimeline.tsx → DRVP_ICONS`
4. Add detail extraction case in `extractDrvpDetail()` switch
5. If it affects agent visual state, add handler in `drvp-consumer.ts`

### Adding a New Agent Status

1. Add to `AgentVisualStatus` type in `gateway/types.ts`
2. Add color to `STATUS_COLORS` in `lib/constants.ts`
3. Add animation keyframe to `styles/globals.css` (if animated)
4. Map in `AgentAvatar.tsx` (ring animation selection)
5. Map in `AgentCharacter.tsx` (3D opacity/behavior)
6. Map in `event-parser.ts` (gateway event → status)
7. Map in `drvp-consumer.ts` (DRVP event → status)
