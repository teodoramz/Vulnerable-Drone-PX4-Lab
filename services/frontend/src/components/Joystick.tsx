import { useRef } from "react";

const MAX_R = 46;
const CENTER = 65;
const MAX_SPEED = 15.0; // m/s

/** Virtual joystick → horizontal NED velocity. Calls onChange(north, east). */
export default function Joystick({
  disabled,
  onChange,
}: {
  disabled: boolean;
  onChange: (north: number, east: number) => void;
}) {
  const knobRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);

  function update(clientX: number, clientY: number, zone: HTMLDivElement) {
    const rect = zone.getBoundingClientRect();
    let x = clientX - rect.left - CENTER;
    let y = clientY - rect.top - CENTER;
    const dist = Math.hypot(x, y);
    if (dist > MAX_R) {
      x *= MAX_R / dist;
      y *= MAX_R / dist;
    }
    if (knobRef.current) knobRef.current.style.transform = `translate(${x}px, ${y}px)`;
    // up on screen = north (+), right = east (+)
    onChange(-(y / MAX_R) * MAX_SPEED, (x / MAX_R) * MAX_SPEED);
  }

  function reset() {
    draggingRef.current = false;
    if (knobRef.current) knobRef.current.style.transform = "translate(0px, 0px)";
    onChange(0, 0);
  }

  return (
    <div
      className={`joystick-zone ${disabled ? "opacity-30 pointer-events-none" : ""}`}
      onPointerDown={(e) => {
        draggingRef.current = true;
        (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
        update(e.clientX, e.clientY, e.currentTarget);
      }}
      onPointerMove={(e) => {
        if (draggingRef.current) update(e.clientX, e.clientY, e.currentTarget);
      }}
      onPointerUp={reset}
      onPointerLeave={() => draggingRef.current && reset()}
    >
      <div ref={knobRef} className="joystick-knob" />
    </div>
  );
}
