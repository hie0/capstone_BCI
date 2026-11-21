# Recorded EEG on Vercel

Vercel serves the Vite frontend and `public/recorded-eeg/` assets. Browser playback does not call Python, REST `/api`, or WebSocket `/ws` in the default static mode. Existing fitted models generated the results locally; this is replay of actual predictions, not inference running on Vercel or in the browser.

## Vercel project settings

- Repository: `hie0/capstone_BCI`
- Root Directory: `website`
- Framework Preset: Vite
- Install Command: `npm ci`
- Build Command: `npm run build`
- Output Directory: `dist`
- Environment: `VITE_BCI_RECORDED_SOURCE=static` (also the default when no Backend URL is set)
- Leave `VITE_BCI_API_BASE` empty for static replay.
- Select the intended deployment branch in the Vercel dashboard; local configuration does not change it or publish automatically.

`website/vercel.json` provides the Vite settings. The app uses HashRouter, so no catch-all rewrite should turn missing JSON assets into HTML. The build verifies SHA256 and complete trial/configuration coverage. Manifest requests revalidate on every configuration/start; the mutable manifest is never retained indefinitely in memory. If an asset is replaced between requests, the loader refreshes the manifest and retries the asset once with full size/SHA256 verification. Removed sessions refresh the selector and pause for the user to confirm the next session. Communication displays load errors alongside playback controls. Replay filenames include content hashes. Only the selected configuration is downloaded, and at most four configurations are retained in the browser's in-memory cache.

## Generate results locally

From the repository root, using the existing research Python environment and local EEG path:

```sh
backend/.venv/bin/python -m backend.export_recorded_replay
```

The script reuses `backend/inference_engine.py` and the current five joblib files. It performs no training, overwrites no model or original EEG files, and preserves chronological CausalEA / Logit Centering and the exported Quality Gate. It exports all 8 selected sessions / 360 online trials in four configurations: 16ch / Low Channel × TTA OFF / ON (32 files, 1,440 predictions).

Low Channel now resolves the existing fitted `5ch__tta_off/on` models for KGE and OYJ and `7ch__tta_off/on` models for WMJ and KHY. Channel counts stay fixed across all selected sessions and both TTA settings. The original variable-count `low__tta_*` model selections are no longer used for website playback. No model is retrained or renamed; inference is regenerated using the saved models, and API session metadata uses the same routing. The 16ch exports are unchanged. Montage/reference/filter/window can still differ between the saved models; this is not a controlled TTA-only ablation. In particular, some saved 5ch models use C3/Cz/C4/P7/P8 (Core) rather than the research PM montage. Active electrode positions always reflect the actual fitted model. Research-page benchmark results are unchanged.

The following sessions are excluded from both public replay and live Backend selection: `kge_online0928_01`, `wmj_online0930_03`, `oyj_online0929_02`, and `khy_online0930_03`. Original EEG, logs and fitted research models remain intact. Their previously deployed replay assets were backed up under the private local cache and removed from the public directory. Remaining replay files are byte-for-byte unchanged. Each participant now has two selectable sessions.

For existing replay exports, `backend/.venv/bin/python -m backend.add_replay_history` adds only measured pre-trial display history, updates content hashes, and preserves every existing prediction field without rerunning inference. Retired generated files are backed up in the private local cache. The regular export command also includes this history.

Public files contain allowlisted participant initials, session IDs, active channels, actual predictions/probabilities, labels for evaluation, Quality Gate, measured export-time inference latency, and the Backend's existing filtered/rounded display snippets (250 points per channel per trial, plus 500 measured pre-trial points per channel once per configuration). They do not contain complete original EEG CSVs, calibration logs, personal names, absolute paths, fitted states, or joblib files. Display snippets are derived EEG data and become publicly accessible with the deployed site. Ground truth scores the replay and game targets; it never replaces model predictions for commands.

Private source hashes and per-condition validation metrics remain in ignored `backend/local_cache/recorded-export/`. First/final trial predictions, scores, quality and waveforms are checked against the existing single-trial chronological inference path; run-to-run latency is excluded from equality checks. Source hashes allow subsequent exports to reuse verified assets without repeating inference.

## Playback behavior

Participant/session/channel/TTA select their corresponding asset. Start, Pause, Reset and speed operate on the chronological trial cursor. Resume continues with the next trial; there is no fresh TTA initialization at a pause because all causal predictions were generated in order. Missing, corrupt or unsupported assets stop playback explicitly and never substitute synthetic EEG or a different model. Accuracy / BA only include trials already played. Export-time inference latency is labelled as such, rather than presented as browser inference speed. Measured waveform snippets start with a populated real-signal window and scroll continuously on a high-DPI Canvas, using a dedicated OffscreenCanvas worker where available (with a main-thread Canvas fallback). Animation follows display frames rather than updating SVG paths or React state. Snippets follow the replay clock (2 seconds per snippet for the home monitor, 6.6 seconds for the game at 1×). Trial boundaries retain a short gap: the display does not fabricate a continuous signal across separately extracted trial windows. Pause freezes the waveform cursor and resume continues it.

The existing game consumes the shared predictions. Its recorded EEG target comes from trial labels, while movement comes from predicted direction; quality rejection remains in effect. Neuro Runner waits for approach, judgment and passing to finish before requesting the next trial. At 1×, recorded approach takes 4.5 seconds, followed by 0.9 seconds of feedback and 1.2 seconds of passing. Pause preserves the current trial. All modes start with three lives; each clean incorrect prediction costs one life, while rejected trials do not. Obstacle meshes and materials stay mounted. Between trials they reset outside the visible area, then emerge through distant fog; they never travel visibly backwards. Frame-by-frame progress uses a ref instead of re-rendering the React page.

## BCI Communication

Recorded mode uses the same exported model predictions and real waveforms. Each quality-passing prediction moves the existing selection accumulator by 10 points toward LEFT or RIGHT. The existing 80% UI threshold confirms the tree choice; it is distinct from model probability, which remains in the actual prediction monitor. Ground truth never drives a tree choice. Quality-rejected trials do not change the accumulator.

The consumer acknowledges non-threshold trials after 2 seconds at 1×. A threshold choice advances after its 600ms confirmation and immediately acknowledges that trial; the former 1400ms inter-stage rest is removed. The last accepted direction remains visible across stage changes, while rejected trials still clear the activation and never add evidence. Pause suspends both replay and any pending confirmation. Resume continues that pending action before accepting another trial. Changing participant/session/channel/TTA resets the tree. Reset clears the current replay; Back pauses playback and returns one tree level.

Communication uses a wider 500-sample waveform history and disables automatic catch-up acceleration when snippets arrive. The initial display is filled with 500 measured points from the four seconds immediately before the first online epoch. Static Communication preloads this display history after configuration selection without advancing the prediction cursor or metrics. Start continues with the first trial at a steady buffered display rate (2200ms per snippet at 1×); existing trial-boundary gaps remain. Demo signals animate smoothly at a slower, fixed phase rate independent of direction and tree stage. Other application waveform settings are unchanged.

A terminal selection invokes the browser's Korean TTS and pauses playback. “다음 문장 선택” starts a new root-level selection with subsequent recorded trials, or restarts the session if its last trial was reached. Manual cards and existing speech settings remain available in demo modes. Recorded-mode cards cannot inject manual commands. The speech content is a demonstration mapping from model directions to messages, not a recording of a participant's expressed needs.

Browser validation uses original WMJ replay predictions, including incorrect predictions and artifact-rejected trials, to traverse three tree levels and verify the Korean TTS invocation. It checks pending-decision pause/resume, reset, real metadata, no API/WebSocket requests, no smart-home commands, and preservation of manual tree selection.

## Optional original live Backend

For local research only, set `VITE_BCI_RECORDED_SOURCE=backend` and start the existing FastAPI server. An external API origin can be supplied with `VITE_BCI_API_BASE`. Never point the public Vercel site at `localhost`.

## Verify the deployed build locally

```sh
cd website
npm run build
npx playwright test -c playwright.static.config.ts
```

The preview server serves `dist/` with no API proxy. Tests prohibit API/WebSocket access and check real exported results, participant/session/configuration switching, device commands, pause/resume/reset, error behavior and responsive layouts.

No original EEG or model upload is needed for Vercel. Commit/push and actual Vercel publishing remain separate user-approved actions.
