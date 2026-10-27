import { type FormEvent, useState } from "react";

import { useAuth } from "../auth/AuthContext";
import { DroneMark } from "../components/Brand";
import Button from "../components/ui/Button";
import { inputClass } from "../components/ui/Field";

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username, password);
    } catch {
      setError("Invalid credentials");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="h-full flex items-center justify-center bg-slate-950">
      <div className="w-80">
        <div className="h-1 rounded-t-xl bg-gradient-to-r from-blue-600 via-blue-400 to-transparent" />
        <form
          onSubmit={onSubmit}
          className="bg-slate-900 border border-slate-800 border-t-0 rounded-b-xl p-6 shadow-2xl flex flex-col gap-4"
        >
        <div className="flex items-center gap-3">
          <DroneMark size={30} />
          <div className="leading-none">
            <h1 className="text-lg font-semibold tracking-tight text-slate-100">Sentinel</h1>
            <p className="text-micro uppercase tracking-[0.22em] text-slate-500 mt-1">Airfield Patrol · Sign in</p>
          </div>
        </div>

        {/* Larger inputs than the console's compact controls, via a size override. */}
        <input
          className={`${inputClass} px-3 py-2 text-sm`}
          placeholder="Username"
          value={username}
          autoFocus
          onChange={(e) => setUsername(e.target.value)}
        />
        <input
          type="password"
          className={`${inputClass} px-3 py-2 text-sm`}
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        {error && <div className="text-xs text-red-400">{error}</div>}

        <Button type="submit" variant="primary" disabled={busy} className="py-2 text-sm">
          {busy ? "Signing in…" : "Sign in"}
        </Button>
        {/* Seeded credentials are configuration (see docs/GETTING-STARTED.md). */}
        </form>
      </div>
    </div>
  );
}
