# Ansible: single-host deployment

Deploys the whole lab (db, drone, c2, sensor, gcs) to one Ubuntu/Debian VM as a systemd-managed compose stack in `/opt/drone-lab`.

```
controller                                         target (/opt/drone-lab)
  build-archive.sh -> drone-lab.tar.gz
  ansible-playbook site.yml --ship + unpack-->     source tree
                            --template-->          .env, drone-lab.service
                                                   docker compose build
                                                   systemctl start drone-lab
                            --verify (HTTP)-->     c2 :8000, console :80
```

## Requirements

- Controller: `ansible-core` 2.12 or newer, no collections.
- Target: Ubuntu or Debian, internet access (Docker install, base images, PX4 sources on the `px4` backend's first boot), about 10 GB free disk (about 20 GB for `px4`).

## Deploy

Run from inside `ansible/`.

```bash
cd ansible
cp inventory.yml.example inventory.yml     # edit ansible_host, ansible_user, key or passwords
ansible-playbook site.yml
```

- `inventory.yml` is gitignored because it holds SSH and sudo passwords. Without it the deploy play matches no hosts and exits 0.
- Prefer an SSH key (`ssh-copy-id`), `--ask-pass --ask-become-pass`, or `ansible-vault encrypt_string` over plaintext passwords.
- The archive `roles/drone_lab/files/drone-lab.tar.gz` is rebuilt by `build-archive.sh` on every run (reproducible, so an unchanged tree does not restart the stack). `-e skip_archive=true` reuses the existing file.

## Variables

Defined in `roles/drone_lab/defaults/main.yml`. Override in `inventory.yml` or with `-e`.

```bash
ansible-playbook site.yml -e drone_lab_backend=mock -e drone_lab_console_port=8080
```

| Variable | Default | Purpose |
|---|---|---|
| `drone_lab_backend` | `px4` | `px4` (20-40 min first build) or `mock` (about 2 min) |
| `drone_lab_drone_count` | `1` | Fleet size |
| `drone_lab_home_alt` | `95.0` | Pad elevation |
| `drone_lab_admin_user` / `drone_lab_admin_pass` | `admin` / `Admin1Admin1` | Admin account |
| `drone_lab_seed_demo_users` | `true` | Create operator and observer |
| `drone_lab_operator_user` / `_pass` | `operator` / `Admin1Admin1` | Operator account |
| `drone_lab_observer_user` / `_pass` | `observer` / `Admin1Admin1` | Observer account |
| `drone_lab_jwt_secret` | `change-me-to-a-long-random-secret-string` | JWT secret, deliberately weak |
| `drone_lab_postgres_db` / `_user` / `_pass` | `fleet` / `fleet` / `Admin1Admin1` | Database |
| `drone_lab_sensor_ifaces` | `ot-ops,ot-air` | Suricata capture interfaces |
| `drone_lab_ids_push_token` | `ids-dev-token` | Sensor to C2 shared secret |
| `drone_lab_console_port` | `80` | Published console port (`GCS_HOST_PORT`) |
| `drone_lab_api_port` | `8000` | Published API port (`C2_HOST_PORT`) |
| `drone_lab_deploy_attacker` | `false` | Start the pivot container (`172.30.10.66` / `172.30.20.66`) |
| `drone_lab_preserve_source_ip` | `true` | Set `"userland-proxy": false` in `/etc/docker/daemon.json` (merged) so IDS alerts carry the attacker's real source address. Restarts the Docker daemon and every container on the host. |
| `drone_lab_dir` | `/opt/drone-lab` | Install directory |
| `drone_lab_service` | `drone-lab` | systemd unit name |

Accounts are re-asserted on every boot, so changing a password and redeploying takes effect.

## What it does

1. `site.yml` pre-tasks: build the archive on the controller (runs under any
   `--limit`). `-e skip_archive=true` reuses the existing one.
2. `apt.yml`: install Docker and the Compose plugin; apply `drone_lab_preserve_source_ip`.
3. `deploy.yml`: ship the archive to `drone_lab_dir`, create `captures/`, template `.env`, record the compose `-f` set in `.compose-files`.
4. `service.yml`: install the systemd unit, build images, start the stack.
5. `database.yml`: wait for Postgres, align its password with the configured one, restart the C2 if needed.
6. `verify.yml`: check the C2, console, backend (waits up to 40 min for the PX4 build), public status API, login and the site dataset (15,793 objects).

Compose files used: `docker-compose.yml`, plus `docker-compose.mock.yml` for `mock`, plus `docker-compose.attacker.yml` when `drone_lab_deploy_attacker` is true.

## After deploy

| Item | Address |
|---|---|
| Console | `http://<target>/` |
| Public status API (no credentials) | `http://<target>:8000/api/public/drone` |
| Radio link (unauthenticated MAVLink) | `<target>:14550/udp` |

```bash
systemctl status drone-lab
journalctl -u drone-lab -f
cd /opt/drone-lab && docker compose $(cat .compose-files) ps
```

The toolkit is also at `/opt/drone-lab/tools/exploit.py`.
