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

Participant/session/channel/TTA select their corresponding asset. Start, Pause, Reset and speed operate on the chronological trial cursor. Resume continues with the next trial; there is no fresh TTA initialization at a pause because all causal predictions were generated in order. Missing, corrupt or unsupported assets stop playback explicitly and never substitute synthetic EEG or a different model. Accuracy / BA only include trials already played. Export-time inference latency is labelled as such, rather than presented as browser inference speed.

The existing game consumes the shared predictions. Its recorded EEG target comes from trial labels, while movement comes from predicted direction; quality rejection remains in effect. Game UI/timing rules have not been redesigned by this deployment change.

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
