import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";
import { Spinner } from "./Icons";

type Variant = "primary" | "secondary" | "ghost";
type Size = "md" | "lg";

const BASE =
  "press inline-flex items-center justify-center gap-2 rounded-md font-semibold whitespace-nowrap select-none disabled:cursor-not-allowed";
const VARIANT: Record<Variant, string> = {
  primary: "bg-primary text-on-primary hover:brightness-110 disabled:bg-surface-2 disabled:text-muted",
  secondary: "border border-line-strong bg-surface text-ink hover:border-ink disabled:text-muted",
  ghost: "text-ink hover:bg-surface-2 disabled:text-muted",
};
// 44px is the minimum comfortable touch target (WCAG 2.2 target size, Apple and Material guidance).
const SIZE: Record<Size, string> = { md: "min-h-11 px-4 text-[0.95rem]", lg: "min-h-12 px-6 text-base" };

export const buttonClass = (v: Variant = "primary", s: Size = "md", extra = "") => `${BASE} ${VARIANT[v]} ${SIZE[s]} ${extra}`;

type Common = { variant?: Variant; size?: Size; children: ReactNode };

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  className = "",
  children,
  disabled,
  ...rest
}: Common & { loading?: boolean } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={buttonClass(variant, size, className)} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading && <Spinner size={18} />}
      {children}
    </button>
  );
}

export function LinkButton({
  variant = "secondary",
  size = "md",
  className = "",
  children,
  ...rest
}: Common & AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a className={buttonClass(variant, size, className)} {...rest}>
      {children}
    </a>
  );
}
