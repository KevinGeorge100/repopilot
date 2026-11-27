// Checks the design tokens in app/globals.css against WCAG 2.2 AA. Run: npm run a11y:contrast
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
const block = (sel) => {
  const m = css.match(new RegExp(`${sel.replace(/[.[\]]/g, "\\$&")}\\s*\\{([^}]*)\\}`));
  if (!m) throw new Error(`no ${sel} block`);
  return Object.fromEntries([...m[1].matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map((x) => [x[1], x[2]]));
};
const themes = { light: block(":root"), dark: block(':root[data-theme="dark"]') };

const lum = (hex) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a, b) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

// [foreground token, background token, minimum ratio, what it is]
const PAIRS = [
  ["ink", "bg", 4.5, "body text on page"],
  ["ink", "surface", 4.5, "body text on cards"],
  ["muted", "bg", 4.5, "secondary text on page"],
  ["muted", "surface", 4.5, "secondary text on cards"],
  ["muted", "surface-2", 4.5, "secondary text on tinted panels"],
  ["link", "bg", 4.5, "links on page"],
  ["link", "surface", 4.5, "links on cards"],
  ["on-primary", "primary", 4.5, "primary button label"],
  ["on-marker", "marker", 4.5, "text on highlighter"],
  ["verified", "surface", 4.5, "verified text"],
  ["alert", "surface", 4.5, "error text"],
  ["alert", "bg", 4.5, "error text on page"],
  ["code-ink", "night", 4.5, "code text on code window"],
  ["code-muted", "night", 4.5, "line numbers on code window"],
  ["marker", "night", 3, "highlighter against code window (non-text)"],
  ["focus", "bg", 3, "focus ring on page (non-text)"],
  ["focus", "surface", 3, "focus ring on cards (non-text)"],
  ["line-strong", "surface", 3, "input borders (non-text)"],
];

let bad = 0;
for (const [name, t] of Object.entries(themes)) {
  for (const [fg, bg, min, what] of PAIRS) {
    if (!t[fg] || !t[bg]) throw new Error(`${name}: missing token ${!t[fg] ? fg : bg}`);
    const r = ratio(t[fg], t[bg]);
    const ok = r >= min;
    if (!ok) bad++;
    console.log(`${ok ? "ok  " : "FAIL"} ${name.padEnd(5)} ${r.toFixed(2).padStart(5)} (min ${min})  ${what}  [${fg} ${t[fg]} on ${bg} ${t[bg]}]`);
  }
}
if (bad) {
  console.error(`\n${bad} contrast failure(s)`);
  process.exit(1);
}
console.log("\nAll token pairs meet WCAG 2.2 AA.");
