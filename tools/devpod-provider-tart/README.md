# DevPod Machine Provider for Tart (`T179`)

Canonical DevPod custom machine provider backed by [Tart](https://tart.run) (`cirruslabs/tart`) for Apple Silicon hosts.

## Architectural Boundary & Hardware Ceiling (`T179` / `T180` / `T368`)

- **Linux-only for DevPod (`T179` AC4):** DevPod's `docker` and `kubernetes` drivers require a container runtime inside the target machine. On M1 Max hardware, Apple's `Virtualization.framework` does not expose nested hardware virtualization to guests (`kern.hv_support=0` inside the VM; nested virtualization requires M3+). Consequently, a macOS guest cannot boot Docker Desktop, Colima, Podman Machine, or `apple/container`.
- **Fail-fast guard:** The `create` verb inspects `TART_IMAGE` **before** `tart clone` and refuses any image matching `macos` (exit code `1`), preventing a 50 GB image pull that would fail 40 minutes later at `docker` initialization.
- **macOS Agent Sandboxes (`T180`):** Coding agents running natively inside a macOS sandbox do not need Docker; they use SSH and `tart exec` via `python3 scripts/tart_sandbox.py`.
- **Opt-in Credentials (`T179` AC5 / `T171`):** `INJECT_GIT_CREDENTIALS` and `INJECT_DOCKER_CREDENTIALS` both default to `"false"` so sandboxes never inherit ambient host credentials unless explicitly granted.

## Registration & Usage

```bash
# Register provider without changing default provider
devpod provider add tools/devpod-provider-tart/provider.yaml --name tart --use=false

# Launch a Linux devcontainer workspace on Tart
devpod up . --provider tart
```

## Verification

```bash
python3 -m unittest wom7web/project/scripts/tests/test_devpod_tart_provider.py
```
