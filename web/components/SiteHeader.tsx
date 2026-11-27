import Link from "next/link";
import { Github, Logo } from "@/components/ui/Icons";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { LinkButton } from "@/components/ui/Button";

export const SOURCE_URL = "https://github.com/KevinGeorge100/repopilot";

const NAV = [
  { href: "#try", label: "Try it" },
  { href: "#uses", label: "Use cases" },
  { href: "#how", label: "How it works" },
  { href: "#faq", label: "FAQ" },
];

export function SiteHeader() {
  return (
    <header className="glass sticky top-0 z-30 border-b border-line">
      <div className="shell flex h-16 items-center justify-between gap-4">
        <Link href="/" className="flex items-center gap-2.5 rounded-md font-bold tracking-tight" aria-label="RepoPilot home">
          <Logo />
          <span className="text-lg">RepoPilot</span>
        </Link>
        <nav aria-label="Sections" className="hidden items-center gap-1 md:flex">
          {NAV.map((n) => (
            <a key={n.href} href={n.href} className="press inline-flex min-h-11 items-center rounded-md px-3 text-muted hover:bg-surface-2 hover:text-ink">
              {n.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-1">
          <a
            href={SOURCE_URL}
            className="press inline-flex h-11 items-center gap-2 rounded-md px-3 text-ink hover:bg-surface-2"
            aria-label="RepoPilot on GitHub"
          >
            <Github />
            <span className="hidden lg:inline">GitHub</span>
          </a>
          <ThemeToggle />
          <LinkButton href="#try" variant="primary" className="ml-1 hidden sm:inline-flex">
            Try it
          </LinkButton>
        </div>
      </div>
    </header>
  );
}
