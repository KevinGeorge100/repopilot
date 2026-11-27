import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RepoPilot: ask questions about code, check the answers",
  description: "Ask a public GitHub repo anything. Every answer points to the exact lines of code behind it, and every citation is verified.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f6fb" },
    { media: "(prefers-color-scheme: dark)", color: "#080c19" },
  ],
};

// Runs before first paint so there is no flash of the wrong theme. Falls back to the system setting.
const THEME_INIT = `try{var t=localStorage.getItem("repopilot.theme");if(t!=="light"&&t!=="dark"){t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body>
        <a
          href="#main"
          className="absolute left-3 top-3 z-50 -translate-y-24 rounded-md bg-ink px-4 py-2 font-semibold text-bg focus:translate-y-0"
        >
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
