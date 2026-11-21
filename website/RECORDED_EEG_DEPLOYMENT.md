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

`website/vercel.json` provides the Vite settings. The app uses HashRouter, so no catch-all rewrite should turn missing JSON assets into HTML. The build verifies SHA256 and complete trial/configuration coverage. Manifest requests revalidate; replay filenames include content hashes. Only the selected configuration is downloaded, and at most four configurations are retained in the browser's in-memory cache.

## Generate results locally

From the repository root, using the existing research Python environment and local EEG path:

```sh
backend/.venv/bin/python -m backend.export_recorded_replay
```

The script reuses `backend/inference_engine.py` and the current five joblib files. It performs no training, overwrites no model or original EEG files, and preserves chronological CausalEA / Logit Centering and the exported Quality Gate. It exports all 12 selected sessions / 540 online trials in four configurations: 16ch / Low Channel × TTA OFF / ON (48 files, 2,160 predictions).

Public files contain allowlisted participant initials, session IDs, active channels, actual predictions/probabilities, labels for evaluation, Quality Gate, measured export-time inference latency, and the Backend's existing filtered/rounded display snippets (250 points per channel). They do not contain complete original EEG CSVs, calibration logs, personal names, absolute paths, fitted states, or joblib files. Display snippets are derived EEG data and become publicly accessible with the deployed site. Ground truth scores the replay and game targets; it never replaces model predictions for commands.

Private source hashes and per-condition validation metrics remain in ignored `backend/local_cache/recorded-export/`. First/final trial predictions, scores, quality and waveforms are checked against the existing single-trial chronological inference path; run-to-run latency is excluded from equality checks. Source hashes allow subsequent exports to reuse verified assets without repeating inference.

## Playback behavior

Participant/session/channel/TTA select their corresponding asset. Start, Pause, Reset and speed operate on the chronological trial cursor. Resume continues with the next trial; there is no fresh TTA initialization at a pause because all causal predictions were generated in order. Missing, corrupt or unsupported assets stop playback explicitly and never substitute synthetic EEG or a different model. Accuracy / BA only include trials already played. Export-time inference latency is labelled as such, rather than presented as browser inference speed. Measured waveform snippets start with a populated real-signal window and scroll continuously on a high-DPI Canvas, using a dedicated OffscreenCanvas worker where available (with a main-thread Canvas fallback). Animation follows display frames rather than updating SVG paths or React state. Snippets follow the replay clock (2 seconds per snippet for the home monitor, 6.6 seconds for the game at 1×). Trial boundaries retain a short gap: the display does not fabricate a continuous signal across separately extracted trial windows. Pause freezes the waveform cursor and resume continues it.

The existing game consumes the shared predictions. Its recorded EEG target comes from trial labels, while movement comes from predicted direction; quality rejection remains in effect. Neuro Runner waits for approach, judgment and passing to finish before requesting the next trial. At 1×, recorded approach takes 4.5 seconds, followed by 0.9 seconds of feedback and 1.2 seconds of passing. Pause preserves the current trial. All modes start with three lives; each clean incorrect prediction costs one life, while rejected trials do not. Obstacle meshes and materials stay mounted. Between trials they reset outside the visible area, then emerge through distant fog; they never travel visibly backwards. Frame-by-frame progress uses a ref instead of re-rendering the React page.

## BCI Communication

Recorded mode uses the same exported model predictions and real waveforms. Each quality-passing prediction moves the existing selection accumulator by 10 points toward LEFT or RIGHT. The existing 80% UI threshold confirms the tree choice; it is distinct from model probability, which remains in the actual prediction monitor. Ground truth never drives a tree choice. Quality-rejected trials do not change the accumulator.

The consumer acknowledges each trial after its UI processing (2 seconds at 1×; a threshold choice uses 600ms confirmation plus 1400ms rest). Pause suspends both replay and any pending confirmation. Resume continues that pending action before accepting another trial. Changing participant/session/channel/TTA resets the tree. Reset clears the current replay; Back pauses playback and returns one tree level.

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
