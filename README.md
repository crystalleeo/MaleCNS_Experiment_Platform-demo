# MaleCNS Experiment Platform demo

A self-contained local demo release of the accepted **V5 synchronized Experiment
Platform**: a Three.js viewer, an experiment platform UI, and an activity bridge
that validates every `bodyId` against the frozen MaleCNS v1.0 canonical universe.

- Viewer: <http://127.0.0.1:9205> (1200 visible neurons, 40 active visible neurons
  per frame, 10 FPS, gain `.65`, threshold `.22`, decay `.82`)
- Experiment platform: <http://127.0.0.1:9215> (the 9215 UI embeds the viewer)
- Version: `0.1.0` (pre-release demo)

This demo shows **synchronization plumbing**, not neuroscience: the producer that
feeds the bridge is explicitly a non-scientific demo stream.

## Status: R3A asset URLs verified; R3 re-acceptance pending

Three required viewer assets (`neurons_lines.bin`, `brain_shell.bin`,
`vnc_shell.bin`; manifest ids **A3/A4/A5**) are project-derived release assets.
Their bytes and SHA256 hashes are frozen by the R1 audit and were independently
re-verified after anonymous download from the public immutable GitHub Release
[`assets-v0.1.0`](https://github.com/crystalleeo/MaleCNS_Experiment_Platform-demo/releases/tag/assets-v0.1.0).
They are recorded in `assets/manifest.json` as
`"url_status": "verified_project_release"`.

`./bootstrap.sh` downloads each missing asset only from its recorded public URL,
verifies its exact size and SHA256, and never guesses a URL, copies from a local
source project, or creates a symlink fallback.

## Deployment contract

```bash
# 1. first run only: prepare the environment and resolve assets
./bootstrap.sh
#    (./bootstrap.sh --start bootstraps and then starts, but only after all
#     required assets resolve)

# 2. every run: start viewer 9205 + bridge + platform 9215
./start.sh                 # add --no-open to skip opening the browser

# 3. open the platform and press 运行试验 to run the synchronized demo
#    (the experiment never starts automatically)

# 4. stop everything that this repository started
./stop.sh
```

- `bootstrap.sh` is idempotent, macOS-first, and uses **no sudo and no global
  pip**. It creates a repo-local `.venv` only, installs the minimal demo
  dependencies, and validates assets before anything else can start a server.
- `start.sh` starts the three long-running processes in the accepted order
  (viewer 9205 → activity bridge → platform 9215), records **only its own PIDs**
  under `.runtime/pids/`, refuses to start if a port is held by a foreign
  process, and opens 9215 with the macOS `open` command after health succeeds.
- `stop.sh` signals **only PIDs recorded by this repository** and re-checks that
  each live process command points into this repo before signalling. There are no
  pattern-based termination commands and no port-based blanket kills. The
  platform's `POST /api/shutdown` (the webpage 关闭 button) calls exactly this
  script and still returns its normal JSON response.
- Runtime state lives under `.runtime/` (gitignored): `.runtime/pids/`,
  `.runtime/logs/`, and the activity streams in `.runtime/activity/`.

## Layout

```
bootstrap.sh start.sh stop.sh   process controls (macOS-first, repo-local)
VERSION README.md CITATION.cff  release metadata
LICENSE                         MIT license for project-owned code only
DATA_LICENSE.md                 CC BY 4.0 terms and attribution for A1–A6
THIRD_PARTY_NOTICES.md          Three.js MIT notice for A7–A9
requirements.txt                minimal real demo dependencies
assets/                         manifest.json, download_assets.py, verify_assets.py
config/paths.py                 repo-relative, env-overridable paths
viewer/                         viewer server + accepted static web files
platform/                       FastAPI platform server + accepted static web files
bridge/activity_bridge_v1.py    canonical-universe-validating activity bridge
demo/                           synchronized demo adapter + raw non-scientific producer
data/canonical_body_ids.txt     committed derived data (A1, CC BY 4.0)
scripts/                        check_environment.py, healthcheck.py, clean_runtime.py,
                                run_demo.sh
tests/                          offline smoke tests + fixtures
.runtime/                       runtime state (gitignored, created on demand)
```

All scripts derive the repository root from their own location. There is no
runtime dependency on any developer home directory, external volume, downloads
folder, or the source project.

## Assets

| Id | Path | Deployment | Licence |
|---|---|---|---|
| A1 | `data/canonical_body_ids.txt` | committed, small derived | CC BY 4.0 |
| A2 | `viewer/web/assets/neurons.json` | committed, small derived | CC BY 4.0 |
| A3 | `viewer/web/assets/neurons_lines.bin` | **download** (`verified_project_release`) | CC BY 4.0 |
| A4 | `viewer/web/assets/brain_shell.bin` | **download** (`verified_project_release`) | CC BY 4.0 |
| A5 | `viewer/web/assets/vnc_shell.bin` | **download** (`verified_project_release`) | CC BY 4.0 |
| A6 | `viewer/web/assets/shell_meta.json` | committed, small derived | CC BY 4.0 |
| A7 | `viewer/web/vendor/three.module.js` | committed vendored (Three.js r180) | MIT |
| A8 | `viewer/web/vendor/three.core.js` | committed vendored (Three.js r180) | MIT |
| A9 | `viewer/web/vendor/OrbitControls.js` | committed vendored (Three.js r180) | MIT |

`assets/manifest.json` is the single source of truth: target path, exact size,
exact SHA256, required flag, licence, official parent, and URL status.
`assets/download_assets.py` downloads only when a target is absent or fails
verification, streams into `<target>.part`, verifies SHA256 (and size), then
atomically renames. Large `.bin` assets are gitignored and are never committed,
never put in Git LFS, and never symlinked to the source project.

## Data attribution (CC BY 4.0)

The dataset-derived assets A1–A6 are adaptations of **MaleCNS v1.0**, licensed
**CC BY 4.0** (<https://creativecommons.org/licenses/by/4.0/>). Attribution:

- MaleCNS project: <https://male-cns.janelia.org/>
- Berg et al. (2026), *Sexual dimorphism in the complete Drosophila male central
  nervous system connectome*, Cell 189(18), 5504–5526.e15,
  <https://doi.org/10.1016/j.cell.2026.08.015>

R1 recorded two genuine derivation unknowns: the exact ROI sub-dataset pairing
for the brain and VNC shell assets is not byte-verified (the shells are official
MaleCNS ROI data with high confidence). See the R1 reports listed below.

## Licensing boundaries

`LICENSE` applies only to project-owned Python, JavaScript, Shell, HTML, and
CSS code under the MIT License. It does not license MaleCNS source data,
MaleCNS-derived data or geometry, or vendored Three.js files. See
`DATA_LICENSE.md` for CC BY 4.0 attribution and terms for A1–A6, and
`THIRD_PARTY_NOTICES.md` for the Three.js MIT notice covering A7–A9.

## Scope and non-claims

- **No `dynamics_v1` content or claim.** This release contains no dynamics model,
  no dynamics_v1 code, artifacts, or results. The demo producer is explicitly
  non-scientific and only exercises the bridge/platform synchronization path.
- Excluded from the source project: `dynamics_v1/**`, `packed/**` geometry,
  flat-connectome feathers, `migration/**`, `audit/**` (except the frozen R1
  decisions recorded in `assets/manifest.json`), legacy viewers/platforms
  (V4.2/V4.3/V4.4), build/audit tooling, logs, PIDs, caches, `.venv`, `.DS_Store`,
  editor backups, and all runtime JSONL.
- The accepted viewer presentation is preserved byte-for-byte: `viewer/web/`
  (`index.html`, `main.js`, `vendor/*`, committed assets) and `platform/web/`
  are unchanged copies. The only adapted runtime files are Python/shell paths and
  the demo adapter's hard-coded foreign root, which is documented in
  `demo/demo_sync_platform_adapter.py` and `assets/manifest.json`.

## Provenance

`assets/manifest.json`, the asset table above, and the derivation parameters were
taken from the read-only R0/R1 audit reports in the source project:

- `audit/github_release/R0_RELEASE_AUDIT.md` / `.json`
- `audit/github_release/R1_DATA_PROVENANCE.md` / `.json`
- `audit/github_release/R1_ASSET_PROVENANCE.json`

The R1 decision is binding: commit A1/A2/A6 and A7–A9; treat A3/A4/A5 as release
assets whose hashes are frozen and whose stable URLs are bound to the immutable
`assets-v0.1.0` Release in `assets/manifest.json`.

## Troubleshooting

| Symptom | Meaning / action |
|---|---|
| `ASSET_URL_UNRESOLVED: asset A3 …` | The checked-out manifest lacks a verified project Release URL. Use the current repository version; do not guess a URL or copy from a source project. |
| `missing …/.venv/bin/python3` | Run `./bootstrap.sh` first. |
| `port 9205/9215 is held by another process` | Stop the foreign process yourself; this repo never kills processes it did not start. |
| `healthcheck exit=6` | A Python dependency is missing: re-run `./bootstrap.sh`. |
| Stale PIDs or logs | `python3 scripts/clean_runtime.py --dry-run` then re-run without `--dry-run`. |
