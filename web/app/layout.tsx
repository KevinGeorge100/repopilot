import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RepoPilot: ask questions about code, check the answers",
  description: "Ask a public GitHub repo anything. Every answer points to the exact lines of code behind it, and every citation is verified.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#f4f6fb",
};

// Runs before first paint so there is no flash of the wrong theme. Light is the default; a visitor's own choice (the toggle) is remembered.
const THEME_INIT = `try{var t=localStorage.getItem("repopilot.theme");if(t!=="dark"){t="light"}document.documentElement.dataset.theme=t}catch(e){}`;

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
