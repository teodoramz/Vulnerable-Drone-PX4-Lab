/** Quadrotor mark - the product logo, used in the header and on the login. */
export function DroneMark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className="text-blue-400" aria-hidden>
      <g fill="none" stroke="currentColor" strokeWidth="1.6">
        <circle cx="5" cy="5" r="2.4" />
        <circle cx="19" cy="5" r="2.4" />
        <circle cx="5" cy="19" r="2.4" />
        <circle cx="19" cy="19" r="2.4" />
        <path d="M6.7 6.7 17.3 17.3M17.3 6.7 6.7 17.3" strokeLinecap="round" />
      </g>
      <circle cx="12" cy="12" r="2.6" className="fill-blue-500" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <div className="leading-none">
      <div className="font-semibold tracking-tight text-slate-100">Sentinel</div>
      <div className="text-[9px] uppercase tracking-[0.22em] text-slate-500">Airfield Patrol</div>
    </div>
  );
}
