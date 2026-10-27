import type { ClickMode } from "../../features/fleet/useMissionPlanner";
import Button from "../ui/Button";
import Toggle from "../ui/Toggle";

const CLICK_MODE_ACTIVE: Record<ClickMode, string> = {
  target: "bg-blue-600 text-white",
  perimeter: "bg-blue-600 text-white",
  delete: "bg-red-800 text-white",
};

export default function MapToolbar({
  clickMode,
  onClickMode,
  perimeterCount,
  onUndo,
  onClear,
}: {
  clickMode: ClickMode;
  onClickMode: (m: ClickMode) => void;
  perimeterCount: number;
  onUndo: () => void;
  onClear: () => void;
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <Toggle
        value={clickMode}
        onChange={onClickMode}
        options={[
          { value: "target", label: "Go-to point", activeClassName: CLICK_MODE_ACTIVE.target },
          { value: "perimeter", label: "Draw route", activeClassName: CLICK_MODE_ACTIVE.perimeter },
          { value: "delete", label: "Erase", activeClassName: CLICK_MODE_ACTIVE.delete },
        ]}
      />

      <Button size="sm" onClick={onUndo} disabled={perimeterCount === 0}>
        Undo point
      </Button>
      <Button size="sm" onClick={onClear}>
        Clear all
      </Button>

      <span className="text-label text-slate-500">
        {clickMode === "target"
          ? "Click the map to set a destination."
          : clickMode === "perimeter"
            ? `Click to drop perimeter points (${perimeterCount}).`
            : "Delete mode - click near a point or target to remove it."}
      </span>
    </div>
  );
}
