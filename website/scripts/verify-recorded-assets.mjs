// Build gate: deploying without the generated replay files must fail explicitly.
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
const root = new URL('../public/recorded-eeg/', import.meta.url);
const manifest = JSON.parse(readFileSync(new URL('manifest.json', root), 'utf8'));
if (manifest.schema_version !== 1 || manifest.sessions.length !== 12) throw new Error('Expected 12 exported EEG sessions');
let trials = 0, configurations = 0, predictions = 0;
const lowCounts = { KGE: 5, OYJ: 5, WMJ: 7, KHY: 7 };
for (const session of manifest.sessions) {
  trials += session.n_online_trials;
  for (const key of ['16ch__tta_off', '16ch__tta_on', 'low__tta_off', 'low__tta_on']) {
    const asset = session.replays[key];
    if (!asset || !/^[a-z0-9_-]+\.json$/.test(asset.file)) throw new Error(`Missing replay: ${session.session_id}/${key}`);
    const raw = readFileSync(new URL(asset.file, root));
    if (raw.length !== asset.bytes || createHash('sha256').update(raw).digest('hex') !== asset.sha256) throw new Error(`Invalid replay hash: ${asset.file}`);
    const data = JSON.parse(raw);
    const model = session.available_models[key];
    const expectedCount = key.startsWith('low__') ? lowCounts[session.participant_id] : 16;
    if (model.n_channels !== expectedCount || model.active_channels.length !== expectedCount) throw new Error(`Incorrect channel count: ${session.session_id}/${key}`);
    if (data.participant_id !== session.participant_id || data.session_id !== session.session_id || data.predictions.length !== session.n_online_trials) throw new Error(`Replay identity/count mismatch: ${asset.file}`);
    for (const [index, prediction] of data.predictions.entries()) {
      if (prediction.trial_id !== index + 1 || prediction.playback_source !== 'precomputed') throw new Error(`Invalid trial order: ${asset.file}`);
      if (JSON.stringify(prediction.active_channels) !== JSON.stringify(model.active_channels) || Object.keys(prediction.waveform).length !== expectedCount) throw new Error(`Prediction/channel mismatch: ${asset.file}`);
    }
    configurations++;
    predictions += data.predictions.length;
  }
}
if (trials !== 540 || configurations !== 48 || predictions !== 2160) throw new Error('Incomplete Recorded EEG export');
console.log(`Recorded EEG: ${manifest.sessions.length} sessions, ${trials} trials, ${configurations} configurations, ${predictions} verified predictions.`);
