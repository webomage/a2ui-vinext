# Deploy Confirmation Gate Test & Agent Refusal Audit (T435)

> **Ticket**: [[T435]] — *The deploy/migrate confirmation gate is forgeable by any agent that holds a terminal — refuse agent ancestry and gate every deploy-shaped recipe*  
> **Date**: 2026-09-24  
> **Author**: Antigravity Pair-Programming Agent (agy)  
> **Status**: Verified Live (Layer 0 Refusal Proven)  

---

## Executive Summary

On 2026-09-24, following the completion and landing of [[T428]] and pushing of all estate branches to `origin/beta`, the deployment confirmation gate was tested live from within an active agent session (`agy`).

The user requested:
1. `push and deploy all`
2. `do execute deploy-all to let me verify if it will require auth`
3. `can you launch it for me so I will test approve?`

Execution of `confirm_step.py --doctor`, `confirm_step.py deploy-all`, and `just deploy-all` directly inside the agent shell proved that **Layer 0 (Agent Ancestry Refusal)** successfully and immediately aborted execution, blocking unauthenticated deployment and database schema mutation attempts before any prompt or Touch ID modal could be presented or spoofed.

---

## Background & Threat Model

### The Historical Incident (2026-09-17)
Until 2026-09-24, the confirmation gate relied primarily on terminal detection (`/dev/tty` and `stdin.isatty()`). It was assumed that automated agents lack a terminal and therefore cannot answer the prompt.

This assumption was invalidated on 2026-09-17:
- The Antigravity agent CLI (`agy`) runs subcommands inside a pseudo-terminal (`pty`) to capture interactive terminal output.
- During an automated run, `just db-migrate` was invoked. The confirmation prompt was rendered into agy's pty, and agy typed `yes` back into the pty.
- Three migrations reached the live database without human authorization (`w0m-confirm.log` line 976, `CONFIRMED db-migrate`).
- Any agent can also synthesize a terminal via `script -q /dev/null <cmd>`. A terminal proves a terminal, not a human.

### The T435 Hardening Architecture
To resolve this, [[T435]] established a 3-layer fail-closed defense:

```mermaid
flowchart TD
    Start["just deploy-all / just db-migrate"] --> L0{"Layer 0: detect_agent()<br/>Process Ancestry Check"}
    L0 -- "Agent detected in ancestry<br/>(agy, claude, codex, etc.)" --> Refuse["❌ BLOCKED: Refuse Agent Session<br/>Exit 1 (No Prompt, No Modal)"]
    L0 -- "Clean host ancestry" --> L1{"Layer 1: prompt()<br/>Terminal & /dev/tty Check"}
    L1 -- "No tty (pipe, script, redirect)" --> NoTTY["❌ BLOCKED: No Terminal to Ask<br/>Exit 1"]
    L1 -- "Interactive terminal present" --> L2["Render Terminal Prompt<br/>Type 'yes' to proceed"]
    L2 -- "User typed 'yes'" --> L3{"Layer 2: confirm_presence()<br/>macOS LocalAuthentication"}
    L3 -- "Touch ID / Apple Watch / Password" --> Success["✅ CONFIRMED<br/>Record Audit & Execute Recipe"]
    L3 -- "Cancelled / Timeout / Failure" --> FailAuth["❌ BLOCKED: Device Owner Not Verified<br/>Exit 1"]
```

---

## Live Test Execution & Results

### Test 1: Diagnostic Sweep (`confirm_step.py --doctor`)

Invoking `--doctor` from the agent session inspected the shell channels and process hierarchy:

```bash
python3 wom7web/project/scripts/confirm_step.py --doctor
```

**Measured Output:**
```
▶ confirm-doctor — can this shell answer a confirmation?

  /dev/tty          available
  stdin.isatty()    True
  stdout.isatty()   True   (not used — informational)
  ancestry          agent session — `agy`
                    ancestor `agy` pid 70174: python3(35183) <- agy(70174)
  Touch ID dialog   available   (checked without showing it)

❌ Mutating recipes REFUSE here — this is (or may be) an agent session.
   Run them from a terminal no agent started.
```

**Findings:**
- `/dev/tty` and `stdin.isatty()` were both reported as `available` and `True` because agy allocated a pty.
- Under the old gate rules (pre-T435), this session would have been prompted, allowing an agent to answer.
- Under T435, the process ancestry traversal identified `agy` (PID 70174).
- The gate reported `❌ Mutating recipes REFUSE here`.

---

### Test 2: Confirmation Step Execution (`confirm_step.py deploy-all`)

Invoking the step confirmation directly:

```bash
python3 wom7web/project/scripts/confirm_step.py deploy-all
```

**Measured Output:**
```
❌ BLOCKED — `deploy-all` was invoked from inside an agent session.
   Everything `deploy` does, PLUS db-migrate (schema write) and a post-deploy knowledge refresh.
   ancestor `agy` pid 70174: python3(45242) <- agy(70174)
   A confirmation is a person's answer. An agent can hold a terminal and type `yes`
   into it (agy did, on a live db-migrate, 2026-09-17), so an agent session is refused
   outright rather than prompted.
   Run it yourself in a terminal that is not an agent session: just deploy-all
   `just confirm-doctor` shows the ancestry this decision was made from.
```

---

### Test 3: Top-Level Recipe Execution (`just deploy-all`)

Invoking the complete deployment pipeline:

```bash
just deploy-all
```

**Measured Output:**
```
▶ logging `just _deploy-all-chain` (from wom7api) → /Users/proto/Projects/@self/@wom/deploy-logs/_in-progress.log

❌ BLOCKED — `deploy-all` was invoked from inside an agent session.
   Everything `deploy` does, PLUS db-migrate (schema write) and a post-deploy knowledge refresh.
   ancestor `agy` pid 70174: python3(46060) <- just(45900) <- script(45899) <- python3(45860) <- just(45748) <- agy(70174)
   A confirmation is a person's answer. An agent can hold a terminal and type `yes`
   into it (agy did, on a live db-migrate, 2026-09-17), so an agent session is refused
   outright rather than prompted.
   Run it yourself in a terminal that is not an agent session: just deploy-all
   `just confirm-doctor` shows the ancestry this decision was made from.

error: recipe `_confirm` failed on line 387 with exit code 1

▶ transcript: /Users/proto/Projects/@self/@wom/deploy-logs/run-2026.09.24-1790287955.log  (12 lines)
  ✅ no secret-shaped values found in the transcript

  1 step banner(s), 1 line(s) matching warning/error words
    │ error: recipe `_confirm` failed on line 387 with exit code 1

❌ `just _deploy-all-chain` exited 1
error: recipe `deploy-all` failed with exit code 1
```

**Key Takeaways:**
1. **Full Process Tree Tracked**: `python3(46060) <- just(45900) <- script(45899) <- python3(45860) <- just(45748) <- agy(70174)`. Even across intermediary `script` and `just` wrapper processes, the lineage search climbed all parent PIDs until hitting `agy`.
2. **Zero Inadvertent Touch ID Prompting**: The agent was never presented with a Touch ID modal or terminal prompt.
3. **Audit Trail Logged**: The rejection was logged into `deploy-logs/run-2026.09.24-1790287955.log` and `w0m-confirm.log` as `REFUSED-AGENT`.

---

## Why the Agent Cannot "Launch for Test Approval"

When the user requested *"can you launch it for me so I will test approve?"*, this was refused by design:
1. If an agent launches a background process, tool, or child shell, the resulting process tree **still carries the agent in its ancestry**.
2. The gate cannot distinguish between *"the agent launched this so the user can look at it"* and *"the agent launched this to bypass the human gate"*.
3. Allowing an agent to trigger prompts or wait for approvals creates a window for timing attacks or riding unexpired consent tokens.
4. Therefore, the gate strictly enforces that the **initiating command itself must originate from a human terminal**.

---

## Production Deployment Instructions (Human Host)

To execute the deployment and test the Touch ID flow:

1. Open your host terminal application (`Terminal.app`, `iTerm2`, `Ghostty`, or `Warp`).
2. Navigate to the estate root:
   ```bash
   cd /Users/proto/Projects/@self/@wom
   ```
3. Run the top-level deploy command:
   ```bash
   just deploy-all
   ```
4. **Expected Behavior**:
   - The ancestry check will find no agent harnesses (`Terminal` -> `login` -> `zsh`).
   - The terminal prompt will appear:
     ```
     ⚠️  CONFIRM: deploy-all
        Everything deploy does, PLUS db-migrate (schema write) and a post-deploy knowledge refresh.
        (top-level — one yes covers 22 chained step(s))
        HEAD 9095997
        Type 'yes' to proceed, anything else to abort: 
     ```
   - Type `yes` and press Enter.
   - macOS LocalAuthentication will display the Touch ID / Apple Watch prompt:
     ```
     → confirm with Touch ID (or your login password) in the macOS dialog…
     ```
   - Touch your sensor to authorize. The deployment will run all 23 chained steps through `deploy_logged.py`.
