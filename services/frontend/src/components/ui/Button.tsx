import type { ButtonHTMLAttributes } from "react";

export type ButtonVariant = "primary" | "success" | "danger" | "caution" | "patrol" | "swarm" | "ghost";
export type ButtonSize = "sm" | "md";

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: "bg-blue-600 hover:bg-blue-500 text-white",
  success: "bg-emerald-600 hover:bg-emerald-500 text-white",
  danger: "bg-red-600 hover:bg-red-500 text-white",
  caution: "bg-amber-600 hover:bg-amber-500 text-white",
  patrol: "bg-cyan-700 hover:bg-cyan-600 text-white",
  swarm: "bg-purple-500/10 hover:bg-purple-500/20 border border-purple-500 text-purple-300",
  ghost: "bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 hover:text-slate-100",
};

const SIZE_CLASS: Record<ButtonSize, string> = {
  sm: "px-2 py-1 text-label",
  md: "px-3 py-1.5 text-xs",
};

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

/** Shared styling for every command button. */
export default function Button({ variant = "ghost", size = "md", className = "", ...props }: Props) {
  return (
    <button
      {...props}
      className={`rounded font-bold tracking-wide transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${VARIANT_CLASS[variant]} ${SIZE_CLASS[size]} ${className}`}
    />
  );
}
