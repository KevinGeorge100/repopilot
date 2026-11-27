# RepoPilot design system

A living version is at `/styleguide/` (try the theme toggle). Tokens are in `app/globals.css`; components in
`components/ui/`.

## Principles
1. **The highlighter is the product.** Yellow (`--marker`) means "this is the evidence" and nothing else. Green
   (`--verified`) only ever means a check passed. Cobalt (`--primary`, `--link`) means "you can act on this".
2. **Show, then explain.** The landing page leads with a working example, not a description.
3. **Never colour alone.** A passed check has a tick; a failed citation is struck through and explained.
4. **Calm by default.** One entrance sequence and the highlighter sweep are the only motion that runs on its own.
   Everything else responds to a touch or click. All of it stops under `prefers-reduced-motion`.

## Tokens
Colour tokens come in a light and a dark set (`:root`, `:root[data-theme="dark"]`). `npm run a11y:contrast` reads
both and fails if any text pair drops under WCAG 2.2 AA (4.5:1 for text, 3:1 for borders and focus rings). It runs in CI.

| Token | Use |
|---|---|
| `bg`, `surface`, `surface-2` | page, cards and inputs, tinted panels |
| `ink`, `muted` | primary and secondary text |
| `line`, `line-strong` | dividers; input borders (3:1) |
| `primary`, `on-primary`, `link` | main action and its label; links and citation tags |
| `marker`, `on-marker` | the highlighter and text on it |
| `verified`, `alert` | passed checks; errors and failed checks |
| `night`, `code-ink`, `code-muted` | the code window |

- **Type:** Schibsted Grotesk (interface), Newsreader (answers and intros, for reading), JetBrains Mono (code). Fluid scale:
  `t-display`, `t-h2`, `t-h3`, `t-lead`, `t-small`; body is 16px / 1.6; reading text under 70 characters wide.
- **Space:** 4px grid (Tailwind scale), one fluid section step (`--space-section`), one fluid gutter (`--space-gutter`).
- **Radius:** 6 / 10 / 16 / 24px for chips, inputs, cards, hero surfaces. **Shadow:** two levels. **Motion:** 120 / 240 / 520ms, one ease-out curve.

## Layout and breakpoints
One container (`.shell`, max 84rem, fluid gutters). Content reflows rather than scales:

| Width | Layout |
|---|---|
| under 640 | one column, 44px touch targets, evidence below the answer, sticky ask bar |
| 640 to 1023 | wider cards, two-up carousel |
| 1024 and up (laptop) | two-column hero, answer beside the code window, three-up carousel |
| 1280 and up | wide layouts, more breathing room |

Grids that can shrink use `grid-cols-1` (not an implicit auto column) so long code lines can never widen the page.

## Components (`components/ui/`)
`Button` / `LinkButton` (primary, secondary, ghost; loading; 44px minimum), `Carousel` (scroll-snap, buttons, dots,
pause, no autoplay under reduced motion), `ThemeToggle`, `Icons`. Shared: `RepoForm` (the main call to action),
`Stage` (the live example), `CodeWindow`, `AnswerView`, `ReadingTips`.

## Accessibility checklist (each item has a check)
- Contrast: tokens verified in CI (see above).
- axe-core: zero violations on the landing page and style guide, light and dark, laptop and phone.
- Keyboard: skip link, visible 3px focus ring, scrollable code regions are focusable and labelled, carousel controls are buttons.
- Screen readers: landmarks (`header`, `nav`, `main`, `footer`), one `h1`, labelled inputs, `aria-live` for answers and loading states, carousel roles and "n of N" slide labels.
- Motion: reduced-motion removes animation and autoplay; carousel has a pause button.
