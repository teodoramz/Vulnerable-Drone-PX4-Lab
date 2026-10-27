import { useState } from "react";

import type { IdsAlert } from "../api/types";
import AlertDetail from "../components/ids/AlertDetail";
import AlertList from "../components/ids/AlertList";
import FlowTable from "../components/ids/FlowTable";
import PacketView from "../components/ids/PacketView";
import TrafficBreakdown from "../components/ids/TrafficBreakdown";
import SeverityTiles from "../components/ids/SeverityTiles";
import StatusStrip from "../components/panels/StatusStrip";
import Button from "../components/ui/Button";
import { useDroneRegistry } from "../features/fleet/useDroneRegistry";
import { useFlows } from "../features/ids/useFlows";
import { useBreakdown, useCaptures, usePackets } from "../features/ids/useTraffic";
import { useIdsAlerts } from "../features/ids/useIdsAlerts";
import { useFleetSocketContext } from "../ws/FleetSocketProvider";

type Tab = "alerts" | "flows" | "packets" | "breakdown";

const TAB_LABELS: Record<Tab, string> = {
  alerts: "Alerts",
  flows: "Flows",
  packets: "Packets",
  breakdown: "Breakdown",
};

function alertId(a: IdsAlert): string {
  return `${a.ts}|${a.sid}|${a.src_ip}|${a.src_port}|${a.dest_ip}|${a.dest_port}`;
}

/** The SOC view: what the Suricata sensor sees on the drone link, live. */
export default function Network() {
  const { connected, drones, idsAlerts } = useFleetSocketContext();
  const { registry } = useDroneRegistry(() => {});
  const ids = useIdsAlerts(idsAlerts);
  const flows = useFlows();
  const [selected, setSelected] = useState<IdsAlert | null>(null);
  // Four views, since an operator needs a baseline: flows, packets, breakdown.
  const [tab, setTab] = useState<Tab>("alerts");
  const [mavlinkOnly, setMavlinkOnly] = useState(false);
  const [frozen, setFrozen] = useState(false);

  // Poll only what is on screen.
  const packets = usePackets(2000, mavlinkOnly, frozen || tab !== "packets");
  const breakdown = useBreakdown(tab === "breakdown" ? 3000 : 60000);
  const captures = useCaptures();

  return (
    <div className="h-full flex flex-col p-3 gap-3 min-w-0">
      <div className="flex items-center gap-3 flex-wrap justify-between">
        <StatusStrip connected={connected} registry={registry} drones={drones} />
        <div className="flex items-center gap-2">
          <div className="flex rounded overflow-hidden border border-slate-700">
            {(["alerts", "flows", "packets", "breakdown"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-3 py-1 text-xs ${
                  tab === t ? "bg-slate-600 text-white" : "bg-slate-800 text-slate-400 hover:text-slate-200"
                }`}
              >
                {TAB_LABELS[t]}
                {t === "flows" && flows.flows.length > 0 && (
                  <span className="ml-1.5 text-slate-500">{flows.flows.length}</span>
                )}
                {t === "packets" && packets.packets.length > 0 && (
                  <span className="ml-1.5 text-slate-500">{packets.packets.length}</span>
                )}
              </button>
            ))}
          </div>
          <Button
            size="sm"
            onClick={() => {
              if (tab === "alerts") ids.refresh();
              else if (tab === "flows") flows.refresh();
              else if (tab === "packets") packets.refresh();
              else {
                breakdown.refresh();
                captures.refresh();
              }
            }}
            disabled={tab === "alerts" ? ids.loading : tab === "flows" ? flows.loading : false}
          >
            Refresh
          </Button>
        </div>
      </div>

      {tab === "alerts" && (
        <SeverityTiles counts={ids.counts} severityFilter={ids.severityFilter} onFilter={ids.setSeverityFilter} highPulse={ids.highPulse} />
      )}

      {(tab === "flows" || tab === "packets") && !(tab === "flows" ? flows.reachable : packets.reachable) && (
        <div className="shrink-0 rounded-lg border border-amber-700/60 bg-amber-500/10 px-3 py-2 text-label text-amber-300">
          Live capture unavailable - the sensor could not open a raw socket on its
          interfaces, or is unreachable. Alerts already received still show under Alerts.
          {(tab === "flows" ? flows.error : packets.error) && (
            <span className="block text-amber-400/70 font-mono">
              {tab === "flows" ? flows.error : packets.error}
            </span>
          )}
        </div>
      )}

      {tab === "flows" ? (
        <div className="flex-1 min-h-0 bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
          <FlowTable flows={flows.flows} totals={flows.totals} />
        </div>
      ) : tab === "packets" ? (
        <div className="flex-1 min-h-0 bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
          <PacketView
            packets={packets.packets}
            mavlinkOnly={mavlinkOnly}
            onMavlinkOnly={setMavlinkOnly}
            paused={frozen}
            onPaused={setFrozen}
          />
        </div>
      ) : tab === "breakdown" ? (
        <div className="flex-1 min-h-0">
          <TrafficBreakdown
            byProto={breakdown.by_proto ?? []}
            byPort={breakdown.by_port ?? []}
            mavlinkMessages={breakdown.mavlink_messages ?? []}
            totalPackets={breakdown.total_packets ?? 0}
            totalBytes={breakdown.total_bytes ?? 0}
            captures={captures.captures}
            capturesError={captures.error}
            onDownload={captures.download}
          />
        </div>
      ) : (
      <div className="flex-1 min-h-0 flex gap-3">
        {/* The stream gets most of the width so signatures are readable. */}
        <div className="flex-[3] min-w-[26rem] bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
          <AlertList alerts={ids.alerts} selectedId={selected ? alertId(selected) : null} onSelect={setSelected} />
        </div>
        <div className="flex-[2] min-w-[22rem] bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
          <AlertDetail alert={selected} />
        </div>
      </div>
      )}
    </div>
  );
}
