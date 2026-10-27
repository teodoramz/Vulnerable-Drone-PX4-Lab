interface Option<T extends string> {
  value: T;
  label: string;
  /** Class applied when this specific option is active - lets "Delete" glow red, e.g. */
  activeClassName?: string;
}

interface Props<T extends string> {
  value: T;
  options: Option<T>[];
  onChange: (value: T) => void;
  /** Default active styling when an option has no activeClassName of its own. */
  activeClassName?: string;
}

/** Segmented control used for the map-mode / click-mode switches. */
export default function Toggle<T extends string>({
  value,
  options,
  onChange,
  activeClassName = "bg-slate-600 text-white",
}: Props<T>) {
  return (
    <div className="flex rounded-md overflow-hidden border border-slate-700 shrink-0">
      {options.map((opt) => {
        const active = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`px-2.5 py-1 text-xs font-medium transition-colors ${
              active ? (opt.activeClassName ?? activeClassName) : "bg-slate-800 text-slate-400 hover:text-slate-200"
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
