import { type FormEvent, useEffect, useState } from "react";

import api from "../api/client";
import type { Role, User } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import { inputClass } from "../components/ui/Field";

const ROLES: Role[] = ["admin", "operator", "observer"];

export default function Admin() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("operator");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const r = await api.get<User[]>("/api/users");
    setUsers(r.data);
  }
  useEffect(() => {
    load().catch(() => {});
  }, []);

  function fail(e: any) {
    setError(e?.response?.data?.detail ?? "Request failed");
  }

  async function createUser(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.post("/api/users", { username, password, role });
      setUsername("");
      setPassword("");
      await load();
    } catch (e) {
      fail(e);
    }
  }

  async function patch(id: number, body: object) {
    setError(null);
    try {
      await api.patch(`/api/users/${id}`, body);
      await load();
    } catch (e) {
      fail(e);
    }
  }

  async function remove(id: number) {
    if (!confirm("Delete this user?")) return;
    setError(null);
    try {
      await api.delete(`/api/users/${id}`);
      await load();
    } catch (e) {
      fail(e);
    }
  }

  return (
    <div className="h-full overflow-auto p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-bold mb-4 text-slate-100">User Management</h1>
      {error && <div className="mb-3 text-sm text-red-400">{error}</div>}

      <form onSubmit={createUser} className="flex flex-wrap items-end gap-3 bg-slate-900 border border-slate-800 rounded-xl p-4 mb-6">
        <div className="flex flex-col gap-1">
          <label className="text-label text-slate-400">Username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} className={inputClass} />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-label text-slate-400">Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-label text-slate-400">Role</label>
          <select value={role} onChange={(e) => setRole(e.target.value as Role)} className={inputClass}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
        <Button type="submit" variant="primary" className="px-4 py-1.5">
          Add user
        </Button>
      </form>

      <table className="w-full text-sm border border-slate-800 rounded-xl overflow-hidden">
        <thead className="bg-slate-900 text-slate-400 text-xs">
          <tr>
            <th className="text-left p-2">ID</th>
            <th className="text-left p-2">Username</th>
            <th className="text-left p-2">Role</th>
            <th className="text-left p-2">Active</th>
            <th className="text-right p-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} className="border-t border-slate-800">
              <td className="p-2 text-slate-500">{u.id}</td>
              <td className="p-2">
                {u.username}
                {u.id === me?.id && <span className="ml-2 text-micro text-blue-400">(you)</span>}
              </td>
              <td className="p-2">
                <select
                  value={u.role}
                  onChange={(e) => patch(u.id, { role: e.target.value })}
                  className={inputClass}
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </td>
              <td className="p-2">
                <button onClick={() => patch(u.id, { is_active: !u.is_active })}>
                  <Badge tone={u.is_active ? "success" : "neutral"}>{u.is_active ? "active" : "disabled"}</Badge>
                </button>
              </td>
              <td className="p-2 text-right">
                <Button size="sm" variant="danger" onClick={() => remove(u.id)} disabled={u.id === me?.id}>
                  delete
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
