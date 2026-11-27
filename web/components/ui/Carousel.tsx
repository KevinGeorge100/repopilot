"use client";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Arrow, ArrowLeft, Pause, Play } from "./Icons";

type Props = { label: string; slides: ReactNode[]; autoplayMs?: number };

/**
 * Accessible carousel. Native scroll-snap does the sliding (touch swipe and keyboard scrolling just work);
 * buttons and dots add precise control. Autoplay is opt-out: it never runs for people who prefer reduced motion,
 * pauses while hovered, focused or touched, and has a visible pause button (WCAG 2.2.2).
 */
export function Carousel({ label, slides, autoplayMs = 6500 }: Props) {
  const track = useRef<HTMLDivElement | null>(null);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [held, setHeld] = useState(false);

  const go = useCallback((i: number) => {
    const el = track.current;
    const child = el?.children[i] as HTMLElement | undefined;
    if (!el || !child) return;
    el.scrollTo({ left: child.offsetLeft - el.offsetLeft, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, []);

  // Track which slide is in view from the scroll position.
  useEffect(() => {
    const el = track.current;
    if (!el) return;
    const onScroll = () => {
      const kids = Array.from(el.children) as HTMLElement[];
      let best = 0;
      let dist = Infinity;
      kids.forEach((k, i) => {
        const d = Math.abs(k.offsetLeft - el.offsetLeft - el.scrollLeft);
        if (d < dist) [best, dist] = [i, d];
      });
      setIndex(best);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    setPlaying(!window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }, []);

  useEffect(() => {
    if (!playing || held) return;
    const t = setTimeout(() => go((index + 1) % slides.length), autoplayMs);
    return () => clearTimeout(t);
  }, [playing, held, index, slides.length, autoplayMs, go]);

  return (
    <section
      aria-roledescription="carousel"
      aria-label={label}
      onMouseEnter={() => setHeld(true)}
      onMouseLeave={() => setHeld(false)}
      onFocus={() => setHeld(true)}
      onBlur={() => setHeld(false)}
      onTouchStart={() => setHeld(true)}
    >
      <div ref={track} className="snap-track -mx-[var(--space-gutter)] px-[var(--space-gutter)]" tabIndex={0} aria-live={playing && !held ? "off" : "polite"}>
        {slides.map((s, i) => (
          <div
            key={i}
            role="group"
            aria-roledescription="slide"
            aria-label={`${i + 1} of ${slides.length}`}
            className="snap-item w-[84%] sm:w-[46%] lg:w-[31%]"
          >
            {s}
          </div>
        ))}
      </div>
      <div className="mt-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-1" role="group" aria-label="Choose a slide">
          {slides.map((_, i) => (
            <button
              key={i}
              type="button"
              onClick={() => go(i)}
              aria-label={`Show slide ${i + 1}`}
              aria-current={i === index}
              className="group inline-flex h-11 w-7 items-center justify-center"
            >
              <span className={`h-1.5 rounded-full transition-all duration-300 ${i === index ? "w-6 bg-primary" : "w-1.5 bg-line-strong group-hover:bg-ink"}`} />
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => setPlaying((p) => !p)} className="press inline-flex h-11 w-11 items-center justify-center rounded-md hover:bg-surface-2" aria-label={playing ? "Pause automatic sliding" : "Start automatic sliding"}>
            {playing ? <Pause size={18} /> : <Play size={18} />}
          </button>
          <button type="button" onClick={() => go(Math.max(0, index - 1))} disabled={index === 0} className="press inline-flex h-11 w-11 items-center justify-center rounded-md border border-line-strong hover:border-ink disabled:opacity-40" aria-label="Previous slide">
            <ArrowLeft size={18} />
          </button>
          <button type="button" onClick={() => go(Math.min(slides.length - 1, index + 1))} disabled={index === slides.length - 1} className="press inline-flex h-11 w-11 items-center justify-center rounded-md border border-line-strong hover:border-ink disabled:opacity-40" aria-label="Next slide">
            <Arrow size={18} />
          </button>
        </div>
      </div>
    </section>
  );
}
