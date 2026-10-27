# Attack toolkit

The lab's attack tools. Usage, per-attack behaviour and detection: [docs/ATTACKS.md](../docs/ATTACKS.md). Every module: [docs/SECURITY.md](../docs/SECURITY.md#toolkit).

| File | Purpose |
|---|---|
| `exploit.py` | MAVLink and application-layer modules |
| `hijack.py` | Minimal MAVLink command-injection demo |
| `airport_objects.json` | Site objects and boundary, so MAVLink attacks need nothing from the target |
| `airport_map.jpg` | Map image |
| `mavlink_attacks.sh` | Scripted MAVLink run against team VMs (`DRY_RUN=1` by default; `TEAMS`, `BLIND` env) |
| `requirements.txt` | `pymavlink`, needed only by the MAVLink modules |

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

The folder also works copied out of the repo. Ansible deploys it to `/opt/drone-lab/tools/` on the target. `python3 ../scripts/check-kit-parity.py` checks the copied dataset and map against the originals.

- Target ports: [docs/GETTING-STARTED.md](../docs/GETTING-STARTED.md#ports)
- Attacking from inside the lab networks: [docs/ATTACKS.md](../docs/ATTACKS.md#attacking-from-inside)
- Checking the result: [docs/PUBLIC-API.md](../docs/PUBLIC-API.md)
