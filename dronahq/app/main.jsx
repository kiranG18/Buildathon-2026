const { useState, useEffect, useRef, useCallback } = React;
const { createRoot } = ReactDOM;

const API_BASE = "https://buildathon-2026-production.up.railway.app";
const CADENCE_URL = "https://buildathon-2026-production.up.railway.app/";
const DEMO_ACCOUNTS = [
  { label: "Ava Chen, manager", email: "ava@helix.demo" },
  { label: "Nadia Frost, admin", email: "admin@helix.demo" }
];
const DEMO_PASSWORD = "helix-demo";
const POLL_MS = 8000;
const AGENTS = ["Researcher", "Qualifier", "Sequencer", "Writer", "Responder", "Caller"];
const STAGE_LABEL = { discovered: "Discovered", researched: "Researched", qualified: "Qualified", contacted: "Contacted", engaged: "Engaged", meeting: "Meeting", opportunity: "Opportunity" };
const SESSION_ERRORS = ["no_token", "invalid_token", "token_expired", "unauthorized"];

class ApiError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

async function callApi(method, path, token, payload) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = "Bearer " + token;
  let res;
  try {
    res = await fetch(API_BASE + path, { method, headers, body: payload === undefined ? undefined : JSON.stringify(payload) });
  } catch (e) {
    throw new ApiError("network", "Cannot reach the server.");
  }
  let data;
  try { data = await res.json(); } catch (e) { throw new ApiError("bad_reply", "The server sent an unexpected reply."); }
  if (data && typeof data === "object" && data.error) {
    throw new ApiError(data.error.code || "error", data.error.message || "Something went wrong.");
  }
  if (!res.ok) throw new ApiError("bad_reply", "The server sent an unexpected reply.");
  return data;
}

function relTime(ms, now) {
  if (!ms || !now) return "";
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return Math.round(s / 60) + " min ago";
  if (s < 86400) return Math.round(s / 3600) + " h ago";
  return Math.round(s / 86400) + " d ago";
}

function Pill({ status }) {
  const map = {
    live: ["bg-emerald-50 text-live border-emerald-200", "●", "Live"],
    paused: ["bg-amber-50 text-paused border-amber-200", "❚❚", "Paused"],
    draft: ["bg-white text-neutral-600 border-neutral-300", "○", "Draft"],
    completed: ["bg-neutral-100 text-neutral-600 border-neutral-200", "✓", "Completed"],
    archived: ["bg-neutral-100 text-neutral-600 border-neutral-200", "▣", "Archived"]
  };
  const [cls, icon, word] = map[status] || map.draft;
  return <span className={"inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium " + cls}><span aria-hidden="true">{icon}</span>{word}</span>;
}

function Spinner({ label }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-line border-t-ink" />
      <p className="text-sm text-neutral-600">{label}</p>
    </div>
  );
}

function ErrorRow({ message, onRetry }) {
  return (
    <div role="alert" className="flex items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
      <span>{message}</span>
      {onRetry && <button onClick={onRetry} className="rounded-lg border border-red-300 bg-white px-3 py-1 font-medium hover:bg-red-100">Retry</button>}
    </div>
  );
}

function Tile({ label, value, tone }) {
  return (
    <div className="rounded-2xl border border-line bg-white p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-neutral-500">{label}</div>
      <div className={"mt-1 text-2xl font-semibold " + (tone || "text-ink")}>{value}</div>
    </div>
  );
}

function Toast({ toast, onClose }) {
  if (!toast) return null;
  return (
    <div role="status" className="fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-xl bg-ink px-4 py-3 text-sm text-white shadow-lg">
      <span>{toast.text}</span>
      {toast.action && <button onClick={toast.action} className="rounded-md border border-white/40 px-2 py-0.5 font-medium hover:bg-white/10">{toast.actionLabel}</button>}
      <button onClick={onClose} aria-label="Dismiss" className="text-white/70 hover:text-white">✕</button>
    </div>
  );
}

function ConfirmDialog({ title, body, confirmLabel, danger, onConfirm, onCancel }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-ink">{title}</h2>
        <p className="mt-2 text-sm text-neutral-600">{body}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onCancel} className="rounded-lg border border-line px-4 py-2 text-sm font-medium hover:bg-neutral-50">Cancel</button>
          <button onClick={onConfirm} className={"rounded-lg px-4 py-2 text-sm font-medium text-white " + (danger ? "bg-red-600 hover:bg-red-700" : "bg-ink hover:bg-black")}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

function SignIn({ onSignedIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});

  async function submit(e, creds) {
    if (e) e.preventDefault();
    const em = (creds ? creds.email : email).trim();
    const pw = creds ? creds.password : password;
    const errs = {};
    if (!em || !em.includes("@")) errs.email = "Enter your work email.";
    if (!pw) errs.password = "Enter your password.";
    setFieldErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    setError("");
    try {
      const data = await callApi("POST", "/auth/login", "", { email: em, password: pw });
      if (!data.token) throw new ApiError("bad_reply", "The server sent an unexpected reply.");
      onSignedIn(data.token, data.user);
    } catch (err) {
      setError(err.code === "network" ? "Cannot reach the server. Try again in a moment." : "Email or password is wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full items-center justify-center bg-cream p-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-2xl border border-line bg-white p-6 shadow-sm" noValidate>
        <div className="mb-5 flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-ink text-base font-semibold text-white">C</span>
          <div>
            <h1 className="text-lg font-semibold text-ink">Cadence</h1>
            <p className="text-xs text-neutral-500">Autonomous outreach with a human in control</p>
          </div>
        </div>
        <label className="block text-sm font-medium text-ink" htmlFor="email">Email</label>
        <input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} className={"mt-1 w-full rounded-lg border px-3 py-2 text-sm " + (fieldErrors.email ? "border-red-400" : "border-line")} />
        {fieldErrors.email && <p className="mt-1 text-xs text-red-700">{fieldErrors.email}</p>}
        <label className="mt-3 block text-sm font-medium text-ink" htmlFor="password">Password</label>
        <input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className={"mt-1 w-full rounded-lg border px-3 py-2 text-sm " + (fieldErrors.password ? "border-red-400" : "border-line")} />
        {fieldErrors.password && <p className="mt-1 text-xs text-red-700">{fieldErrors.password}</p>}
        {error && <div role="alert" className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>}
        <button type="submit" disabled={busy} className="mt-4 w-full rounded-lg bg-ink px-4 py-2.5 text-sm font-medium text-white hover:bg-black disabled:opacity-60">{busy ? "Signing in" : "Sign in"}</button>
        <div className="mt-5 border-t border-line pt-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500">Demo accounts</p>
          <div className="flex flex-col gap-2">
            {DEMO_ACCOUNTS.map((a) => (
              <button key={a.email} type="button" disabled={busy} onClick={() => submit(null, { email: a.email, password: DEMO_PASSWORD })} className="rounded-lg border border-line px-3 py-2 text-left text-sm hover:bg-neutral-50 disabled:opacity-60">{a.label}</button>
            ))}
          </div>
        </div>
      </form>
    </div>
  );
}

function usePolling(loader, deps) {
  const [state, setState] = useState({ loading: true, error: "", data: null });
  const alive = useRef(true);
  const load = useCallback(async () => {
    try {
      const data = await loader();
      if (alive.current) setState({ loading: false, error: "", data });
    } catch (err) {
      if (!alive.current) return;
      if (SESSION_ERRORS.includes(err.code)) { setState({ loading: false, error: "session", data: null }); return; }
      setState((s) => ({ loading: false, error: err.code === "network" ? "Cannot reach the server. Retrying in a few seconds." : err.message, data: s.data }));
    }
  }, deps);
  useEffect(() => {
    alive.current = true;
    setState({ loading: true, error: "", data: null });
    load();
    const t = setInterval(load, POLL_MS);
    return () => { alive.current = false; clearInterval(t); };
  }, [load]);
  return { ...state, reload: load };
}

function CommandCenter({ token, onOpenCampaign, onSession, notify, kill, reloadKill }) {
  const { loading, error, data, reload } = usePolling(async () => {
    const [camps, feed, approvals, escalations, sig] = await Promise.all([
      callApi("GET", "/campaigns", token),
      callApi("GET", "/activity?limit=20", token),
      callApi("GET", "/approvals", token),
      callApi("GET", "/escalations", token),
      callApi("GET", "/state/sig", token)
    ]);
    return { camps, feed: feed.items || [], approvals: approvals.length, escalations: escalations.length, now: sig.now };
  }, [token]);
  const [confirm, setConfirm] = useState(false);

  useEffect(() => { if (error === "session") onSession(); }, [error]);

  async function setKill(active) {
    setConfirm(false);
    try {
      await callApi("POST", "/kill-switch", token, { active, reason: active ? "Stopped from the DronaHQ app" : "Resumed from the DronaHQ app" });
      await reloadKill();
      notify(active ? "Everything is stopped." : "Platform resumed.");
    } catch (err) {
      notify("Could not change the kill switch. Nothing was changed.");
    }
  }

  if (loading) return <Spinner label="Loading the Command Center" />;
  if (!data) return <ErrorRow message={error || "Could not load."} onRetry={reload} />;
  const live = data.camps.filter((c) => c.status === "live").length;
  const inFlight = data.camps.reduce((n, c) => n + (c.counts ? c.counts.prospects : 0), 0);
  const replies = data.camps.reduce((n, c) => n + (c.counts ? c.counts.replies : 0), 0);
  const meetings = data.camps.reduce((n, c) => n + (c.counts ? c.counts.meetings : 0), 0);
  const names = Object.fromEntries(data.camps.map((c) => [c.id, c.name]));

  return (
    <div className="flex flex-col gap-5">
      {error && <ErrorRow message={error} onRetry={reload} />}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-ink">Command Center</h2>
          <p className="text-sm text-neutral-500">Everything running right now, refreshed every few seconds.</p>
        </div>
        {kill && kill.active ? (
          <button onClick={() => setKill(false)} className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-white hover:bg-black">Resume platform</button>
        ) : (
          <button onClick={() => setConfirm(true)} className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700">Stop all</button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Tile label="Live campaigns" value={live} tone="text-live" />
        <Tile label="Prospects" value={inFlight} />
        <Tile label="Replies" value={replies} />
        <Tile label="Meetings" value={meetings} />
        <Tile label="Needs you" value={data.approvals + data.escalations} tone={data.approvals + data.escalations ? "text-paused" : "text-ink"} />
      </div>
      <div className="grid gap-5 lg:grid-cols-3">
        <section className="lg:col-span-1">
          <h3 className="mb-2 text-sm font-semibold text-ink">Campaigns</h3>
          <div className="flex flex-col gap-2">
            {data.camps.map((c) => (
              <button key={c.id} onClick={() => onOpenCampaign(c.id)} className={"flex items-center justify-between gap-2 rounded-xl border p-3 text-left hover:bg-neutral-50 " + (c.status === "paused" ? "border-amber-200 bg-amber-50/50" : "border-line bg-white")}>
                <span className="text-sm font-medium text-ink">{c.name}</span>
                <Pill status={c.status} />
              </button>
            ))}
          </div>
        </section>
        <section className="lg:col-span-2">
          <h3 className="mb-2 text-sm font-semibold text-ink">Live feed</h3>
          {data.feed.length === 0 ? (
            <div className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-neutral-500">No activity yet. Activate a campaign to see agents work.</div>
          ) : (
            <ul className="divide-y divide-line rounded-xl border border-line bg-white">
              {data.feed.map((a) => (
                <li key={a.id} className="flex items-start justify-between gap-3 px-4 py-2.5">
                  <div>
                    <p className="text-sm text-ink">{a.summary}</p>
                    <p className="text-xs text-neutral-500">{names[a.campaign_id] || a.campaign_id}{a.agent_key ? " · " + a.agent_key : ""}</p>
                  </div>
                  <span className="shrink-0 text-xs text-neutral-500">{relTime(a.ts, data.now)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
      {confirm && <ConfirmDialog danger title="Stop all outreach?" body="This stops every autonomous action on every campaign. Your data stays and in-flight jobs are held. You can resume the platform at any time." confirmLabel="Stop everything" onConfirm={() => setKill(true)} onCancel={() => setConfirm(false)} />}
    </div>
  );
}

function CampaignList({ token, onOpenCampaign, onSession, notify }) {
  const [filter, setFilter] = useState("all");
  const [busyId, setBusyId] = useState("");
  const { loading, error, data, reload } = usePolling(async () => {
    const [camps, sig] = await Promise.all([callApi("GET", "/campaigns", token), callApi("GET", "/state/sig", token)]);
    return { camps, now: sig.now };
  }, [token]);

  useEffect(() => { if (error === "session") onSession(); }, [error]);

  async function toggle(c) {
    setBusyId(c.id);
    const pausing = c.status === "live";
    try {
      await callApi("POST", "/campaigns/" + c.id + (pausing ? "/pause" : "/resume"), token, pausing ? {} : undefined);
      await reload();
      if (pausing) {
        notify("Paused " + c.name + ".", "Undo", async () => {
          try { await callApi("POST", "/campaigns/" + c.id + "/resume", token); await reload(); notify("Resumed " + c.name + "."); } catch (e) { notify("Could not resume " + c.name + "."); }
        });
      } else {
        notify("Resumed " + c.name + ".");
      }
    } catch (err) {
      notify("Could not change " + c.name + ". " + err.message);
    } finally {
      setBusyId("");
    }
  }

  if (loading) return <Spinner label="Loading campaigns" />;
  if (!data) return <ErrorRow message={error || "Could not load."} onRetry={reload} />;
  const rows = data.camps.filter((c) => filter === "all" || c.status === filter);

  return (
    <div className="flex flex-col gap-4">
      {error && <ErrorRow message={error} onRetry={reload} />}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold text-ink">Campaigns</h2>
        <div className="inline-flex rounded-lg border border-line bg-white p-0.5 text-sm">
          {["all", "live", "paused", "draft"].map((f) => (
            <button key={f} onClick={() => setFilter(f)} className={"rounded-md px-3 py-1.5 capitalize " + (filter === f ? "bg-ink text-white" : "text-neutral-600 hover:bg-neutral-50")}>{f}</button>
          ))}
        </div>
      </div>
      {rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-line p-10 text-center text-sm text-neutral-500">No {filter === "all" ? "" : filter + " "}campaigns.</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-line bg-white">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="bg-cream text-xs uppercase tracking-wide text-neutral-500">
              <tr><th className="px-4 py-3">Campaign</th><th className="px-4 py-3">Status</th><th className="px-4 py-3 text-right">Prospects</th><th className="px-4 py-3 text-right">Replies</th><th className="px-4 py-3 text-right">Meetings</th><th className="px-4 py-3">Last activity</th><th className="px-4 py-3" /></tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} className={"border-t border-line " + (c.status === "paused" ? "bg-amber-50/60" : c.status === "draft" ? "text-neutral-500" : "")}>
                  <td className="px-4 py-3"><button onClick={() => onOpenCampaign(c.id)} className="text-left font-medium text-ink hover:underline">{c.name}</button><div className="text-xs text-neutral-500">{c.icp_summary}</div></td>
                  <td className="px-4 py-3"><Pill status={c.status} /></td>
                  <td className="px-4 py-3 text-right">{c.counts ? c.counts.prospects : 0}</td>
                  <td className="px-4 py-3 text-right">{c.counts ? c.counts.replies : 0}</td>
                  <td className="px-4 py-3 text-right">{c.counts ? c.counts.meetings : 0}</td>
                  <td className="px-4 py-3 text-xs text-neutral-500">{relTime(c.last_activity, data.now)}</td>
                  <td className="px-4 py-3 text-right">
                    {(c.status === "live" || c.status === "paused") && (
                      <button disabled={busyId === c.id} onClick={() => toggle(c)} className="rounded-lg border border-line bg-white px-3 py-1.5 text-sm font-medium hover:bg-neutral-50 disabled:opacity-60">{c.status === "live" ? "Pause" : "Resume"}</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function CampaignDashboard({ token, campaignId, onBack, onSession, notify }) {
  const [busy, setBusy] = useState("");
  const { loading, error, data, reload } = usePolling(async () => {
    const [dash, camp, sig] = await Promise.all([
      callApi("GET", "/campaigns/" + campaignId + "/dashboard", token),
      callApi("GET", "/campaigns/" + campaignId, token),
      callApi("GET", "/state/sig", token)
    ]);
    return { dash, agents: camp.agents || {}, now: sig.now };
  }, [token, campaignId]);

  useEffect(() => { if (error === "session") onSession(); }, [error]);

  async function toggleCampaign() {
    const pausing = data.dash.campaign.status === "live";
    setBusy("campaign");
    try {
      await callApi("POST", "/campaigns/" + campaignId + (pausing ? "/pause" : "/resume"), token, pausing ? {} : undefined);
      await reload();
      notify(pausing ? "Paused. The other campaigns keep running." : "Resumed.");
    } catch (err) {
      notify("Could not change the campaign. " + err.message);
    } finally {
      setBusy("");
    }
  }

  async function toggleAgent(agent, enabled) {
    setBusy(agent);
    try {
      await callApi("PUT", "/campaigns/" + campaignId + "/agents/" + agent, token, { enabled });
      await reload();
    } catch (err) {
      notify("Could not change " + agent + ". " + err.message);
    } finally {
      setBusy("");
    }
  }

  if (loading) return <Spinner label="Loading the campaign" />;
  if (!data) return <div className="flex flex-col gap-3"><button onClick={onBack} className="self-start text-sm text-neutral-600 hover:underline">← All campaigns</button><ErrorRow message={error || "Could not load."} onRetry={reload} /></div>;
  const { dash, agents } = data;
  const c = dash.campaign;
  const maxCount = Math.max(1, ...dash.funnel.map((f) => f.count));

  return (
    <div className="flex flex-col gap-5">
      <button onClick={onBack} className="self-start text-sm text-neutral-600 hover:underline">← All campaigns</button>
      {error && <ErrorRow message={error} onRetry={reload} />}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold text-ink">{c.name}</h2>
          <Pill status={c.status} />
        </div>
        {(c.status === "live" || c.status === "paused") && (
          <button disabled={busy === "campaign"} onClick={toggleCampaign} className={"rounded-xl px-6 py-3 text-base font-semibold text-white disabled:opacity-60 " + (c.status === "live" ? "bg-paused hover:bg-amber-700" : "bg-live hover:bg-emerald-800")}>{c.status === "live" ? "Pause campaign" : "Resume campaign"}</button>
        )}
      </div>
      {c.status === "paused" && (
        <div role="status" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Paused{c.paused_by ? " by " + c.paused_by : ""}{c.paused_at ? " " + relTime(c.paused_at, data.now) : ""}. {c.held_jobs} job{c.held_jobs === 1 ? "" : "s"} held. Resume to continue.
        </div>
      )}
      {c.status === "draft" && <div className="rounded-xl border border-line bg-white px-4 py-3 text-sm text-neutral-600">Not launched. A draft campaign never sends.</div>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Tile label="Prospects" value={dash.stats.prospects} />
        <Tile label="Contacted" value={dash.stats.contacted} />
        <Tile label="Replies" value={dash.stats.replies} />
        <Tile label="Meetings" value={dash.stats.meetings} />
        <Tile label="Jobs held" value={c.held_jobs} tone={c.held_jobs ? "text-paused" : "text-ink"} />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="rounded-2xl border border-line bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold text-ink">Prospect funnel</h3>
          <div className="flex flex-col gap-2">
            {dash.funnel.map((f) => (
              <div key={f.stage}>
                <div className="flex justify-between text-xs text-neutral-600"><span>{STAGE_LABEL[f.stage] || f.stage}</span><span>{f.count}{f.conversion != null ? " · " + Math.round(f.conversion * 100) + "%" : ""}</span></div>
                <div className="mt-1 h-2 rounded-full bg-cream"><div className="h-2 rounded-full bg-ink" style={{ width: Math.max(2, (f.count / maxCount) * 100) + "%" }} /></div>
              </div>
            ))}
          </div>
        </section>
        <section className="rounded-2xl border border-line bg-white p-4">
          <h3 className="mb-1 text-sm font-semibold text-ink">Agents</h3>
          <p className="mb-3 text-xs text-neutral-500">{dash.agents.running} running · {dash.agents.queued} queued · {dash.agents.failed} failed · {dash.agents.pending_approvals} approvals waiting</p>
          <ul className="divide-y divide-line">
            {AGENTS.map((a) => {
              const on = agents[a] !== false;
              return (
                <li key={a} className="flex items-center justify-between py-2.5">
                  <span className="text-sm text-ink">{a}</span>
                  <button role="switch" aria-checked={on} aria-label={a + (on ? " on" : " off")} disabled={busy === a} onClick={() => toggleAgent(a, !on)} className={"relative h-6 w-11 rounded-full transition disabled:opacity-60 " + (on ? "bg-live" : "bg-neutral-300")}>
                    <span className={"absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all " + (on ? "left-[22px]" : "left-0.5")} />
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      </div>
    </div>
  );
}

function Workspace() {
  const [loaded, setLoaded] = useState(false);
  const [slow, setSlow] = useState(false);
  const timer = useRef(null);
  useEffect(() => {
    timer.current = setTimeout(() => setSlow(true), 12000);
    return () => clearTimeout(timer.current);
  }, []);
  return (
    <div className="relative h-[calc(100dvh-9.5rem)] min-h-[420px] overflow-hidden rounded-xl border border-line bg-white">
      {!loaded && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-white text-center">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-line border-t-ink" />
          <p className="text-sm text-neutral-600">Loading your workspace</p>
          {slow && <p className="text-sm text-neutral-500">Taking longer than usual. <a className="font-medium text-ink underline" href={CADENCE_URL} target="_blank" rel="noopener noreferrer">Open Cadence in a new tab</a></p>}
        </div>
      )}
      <iframe title="Cadence workspace" src={CADENCE_URL} onLoad={() => { clearTimeout(timer.current); setLoaded(true); setSlow(false); }} className="h-full w-full border-0" sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer" />
    </div>
  );
}

function App() {
  const [session, setSession] = useState(null);
  const [screen, setScreen] = useState({ name: "command" });
  const [toast, setToast] = useState(null);
  const [kill, setKill] = useState(null);
  const toastTimer = useRef(null);

  const notify = useCallback((text, actionLabel, action) => {
    clearTimeout(toastTimer.current);
    setToast({ text, actionLabel, action: action ? () => { setToast(null); action(); } : null });
    toastTimer.current = setTimeout(() => setToast(null), 7000);
  }, []);

  const reloadKill = useCallback(async () => {
    if (!session) return;
    try { setKill(await callApi("GET", "/kill-switch", session.token)); } catch (e) { /* the banner stays as it was */ }
  }, [session]);

  useEffect(() => {
    if (!session) return undefined;
    reloadKill();
    const t = setInterval(reloadKill, POLL_MS);
    return () => clearInterval(t);
  }, [session, reloadKill]);

  const signOut = () => { setSession(null); setKill(null); setScreen({ name: "command" }); };

  if (!session) return <div className="h-[100dvh] overflow-hidden"><SignIn onSignedIn={(token, user) => setSession({ token, user })} /></div>;

  const tabs = [["command", "Command Center"], ["campaigns", "Campaigns"], ["workspace", "Full workspace"]];
  const activeTab = screen.name === "campaign" ? "campaigns" : screen.name;
  const token = session.token;

  return (
    <div className="h-[100dvh] overflow-hidden flex flex-col bg-cream">
      <header className="sticky top-0 z-40 border-b border-line bg-cream px-4 pt-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-ink text-sm font-semibold text-white">C</span>
            <h1 className="text-base font-semibold text-ink">Cadence</h1>
          </div>
          <div className="flex items-center gap-3 text-sm text-neutral-600">
            <span className="hidden sm:inline">{session.user.name} · {session.user.role}</span>
            <button onClick={signOut} className="rounded-lg border border-line bg-white px-3 py-1.5 font-medium hover:bg-neutral-50">Sign out</button>
          </div>
        </div>
        <nav className="mt-3 flex gap-1" aria-label="Screens">
          {tabs.map(([key, label]) => (
            <button key={key} onClick={() => setScreen({ name: key })} aria-current={activeTab === key ? "page" : undefined} className={"rounded-t-lg px-4 py-2 text-sm font-medium " + (activeTab === key ? "border-x border-t border-line bg-white text-ink" : "text-neutral-600 hover:text-ink")}>{label}</button>
          ))}
        </nav>
      </header>
      {kill && kill.active && (
        <div role="alert" className="bg-red-600 px-4 py-2 text-center text-sm font-medium text-white">Kill switch active{kill.set_by ? " since it was set by " + kill.set_by : ""}. All outreach is halted.</div>
      )}
      <main className="min-h-0 flex-1 overflow-auto p-4">
        {screen.name === "command" && <CommandCenter token={token} kill={kill} reloadKill={reloadKill} notify={notify} onSession={signOut} onOpenCampaign={(id) => setScreen({ name: "campaign", id })} />}
        {screen.name === "campaigns" && <CampaignList token={token} notify={notify} onSession={signOut} onOpenCampaign={(id) => setScreen({ name: "campaign", id })} />}
        {screen.name === "campaign" && <CampaignDashboard token={token} campaignId={screen.id} notify={notify} onSession={signOut} onBack={() => setScreen({ name: "campaigns" })} />}
        {screen.name === "workspace" && <Workspace />}
      </main>
      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
