"""Export existing fitted models' chronological predictions; never fit or save models.

Public output is an explicit allowlist of UI results and the existing filtered,
rounded display snippets. Original recordings, logs, model states and personal
names stay local. Run from the repository root with backend/.venv/bin/python.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.inference_engine import inference_manager as manager, MODELS_DIR, DATA_ROOT, RECORDED_LOW_CHANNELS

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'website/public/recorded-eeg'
REPORT = ROOT / 'backend/local_cache/recorded-export'
FIELDS = ('trial_id', 'timestamp', 'session_id', 'participant_id',
          'predicted_direction', 'true_direction', 'model_name', 'model_id',
          'active_channels', 'probability_right', 'probability_left',
          'decision_score', 'raw_logit', 'calibrated_logit', 'latency_ms',
          'quality', 'waveform')
QUALITY_FIELDS = ('is_clean', 'status', 'eog_ptp_uv', 'threshold_uv')


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.mkdir(parents=True, exist_ok=True)
    # Source hash audit remains private and contains no raw EEG values.
    sources = {f'models/{p.name}': digest(p) for p in sorted(MODELS_DIR.glob('*.joblib'))}
    for p in sorted(DATA_ROOT.rglob('*.csv')):
        sources[f'online/{p.relative_to(DATA_ROOT)}'] = digest(p)
    for name in ['research_protocol.py', 'recorded_data.py', 'inference_engine.py', 'export_recorded_replay.py']:
        sources[f'backend/{name}'] = digest(ROOT / 'backend' / name)
    source_fingerprint = hashlib.sha256(encode(sources)).hexdigest()
    previous = REPORT / 'validation.json'
    prior_manifest = json.loads((OUTPUT / 'manifest.json').read_text()) if (OUTPUT / 'manifest.json').exists() else {}
    prior_validation = json.loads(previous.read_text()) if previous.exists() else {}
    prior_sources = json.loads((REPORT / 'sources.json').read_text()) if (REPORT / 'sources.json').exists() else {}
    # Reuse verified 16ch exports only when models, data and inference sources
    # match. Export formatting changes alone do not require 16ch inference.
    reusable_sources = {k: v for k, v in sources.items() if k not in
        ('backend/export_recorded_replay.py',)}
    reuse_full = reusable_sources == {k: v for k, v in prior_sources.items() if k not in
        ('backend/export_recorded_replay.py',)}
    if previous.exists() and (OUTPUT / 'manifest.json').exists():
        old = json.loads(previous.read_text())
        manifest = json.loads((OUTPUT / 'manifest.json').read_text())
        assets = [v for s in manifest['sessions'] for v in s['replays'].values()]
        if old.get('source_fingerprint') == source_fingerprint and all(
            (OUTPUT / a['file']).is_file() and digest(OUTPUT / a['file']) == a['sha256'] for a in assets
        ):
            print('Export cache verified: 12 sessions, 540 trials, 48 configurations; no inference repeated.')
            return
    manager.load_all()
    assert len(manager.raw_sessions_map) == 12, 'Expected the selected 12 sessions only'
    assert sum(len(s['on']['y']) for s in manager.raw_sessions_map.values()) == 540
    sessions, validations = [], []
    for subject in ['KGE', 'KHY', 'OYJ', 'WMJ']:
        for entry in manager.sessions_by_subject[subject]:
            sid = entry['session']
            record = {'participant_id': subject, 'session_id': sid,
                      'n_online_trials': len(manager.raw_sessions_map[f'{subject}__{sid}']['on']['y']),
                      'available_models': {}, 'replays': {}}
            for channel in ['16ch', 'low']:
                for tta in [False, True]:
                    key = f'{channel}__tta_{"on" if tta else "off"}'
                    _, model = manager.resolve_calib_model(subject, sid, channel, tta)
                    if channel == 'low':
                        assert len(model.ch_idx) == int(RECORDED_LOW_CHANNELS[subject][0])
                    old_session = next((s for s in prior_manifest.get('sessions', []) if s['session_id'] == sid), {})
                    old_asset = old_session.get('replays', {}).get(key)
                    old_condition = next((v for v in prior_validation.get('conditions', [])
                        if v['session'] == sid and v['configuration'] == key), None)
                    if channel == '16ch' and reuse_full and old_asset and old_condition and digest(OUTPUT / old_asset['file']) == old_asset['sha256']:
                        record['available_models'][key] = old_session['available_models'][key]
                        record['replays'][key] = old_asset
                        validations.append(old_condition)
                        continue
                    result = manager.evaluate_full_session_chronological(subject, sid, channel, tta, include_waveforms=True)
                    predictions = []
                    for i, original in enumerate(result['predictions']):
                        assert original['trial_id'] == i + 1
                        assert original['participant_id'] == subject and original['session_id'] == sid
                        assert original['active_channels'] == model.active_channels
                        item = {k: original[k] for k in FIELDS}
                        item['quality'] = {k: original['quality'][k] for k in QUALITY_FIELDS}
                        item['playback_source'] = 'precomputed'
                        assert set(item['waveform']) == set(item['active_channels'])
                        assert all(len(v) == 250 for v in item['waveform'].values())
                        predictions.append(item)
                    # Compare export against the existing single-trial / WebSocket path,
                    # including causal fast-forward to the final trial.
                    for index in [0, len(predictions) - 1]:
                        check = manager.predict_single_trial(subject, sid, channel, tta,
                            trial_index=index, include_waveform=True,
                            reset_session_state=True, client_key='export-verification')
                        for field in FIELDS:
                            if field == 'latency_ms':
                                continue  # Two actual runs naturally take different time.
                            expected = predictions[index][field]
                            actual = {k: check[field][k] for k in QUALITY_FIELDS} if field == 'quality' else check[field]
                            assert actual == expected, f'{subject}/{sid}/{key}/{index}/{field}'
                    manager.active_online_states.clear()
                    body = {'schema_version': 1, 'participant_id': subject, 'session_id': sid,
                            'channel_mode': channel, 'tta_enabled': tta,
                            'total_trials': len(predictions), 'predictions': predictions}
                    raw = encode(body)
                    sha = hashlib.sha256(raw).hexdigest()
                    filename = f'{sid}-{key}-{sha[:12]}.json'
                    (OUTPUT / filename).write_bytes(raw)
                    record['available_models'][key] = {
                        'montage': model.montage_name, 'active_channels': model.active_channels,
                        'n_channels': len(model.ch_idx), 'band': model.band_name, 'window': model.win_name}
                    record['replays'][key] = {'file': filename, 'sha256': sha, 'bytes': len(raw)}
                    validations.append({'participant': subject, 'session': sid, 'configuration': key,
                        'trials': len(predictions), 'endpoint_equivalence': True,
                        'metrics_all_trials': result['computed_metrics_all_trials'],
                        'metrics_artgate90': result['computed_metrics_artgate90']})
            sessions.append(record)
        print(f'{subject}: exported {sum(s["participant_id"] == subject for s in sessions)} sessions', flush=True)
    assert len(sessions) == 12 and len(validations) == 48
    manifest = {'schema_version': 1, 'kind': 'recorded-model-replay',
        'description': 'Existing Calib20 model predictions replayed in chronological trial order; no browser inference.',
        'waveform': {'kind': 'filtered-display-snippet', 'source_sample_rate_hz': 250,
                     'display_sample_rate_hz': 125, 'samples_per_trial': 250, 'unit': 'uV'},
        'session_count': 12, 'online_trial_count': 540, 'configuration_count': 48,
        'low_channel_counts': {s: int(ch[0]) for s, ch in RECORDED_LOW_CHANNELS.items()},
        'sessions': sessions}
    (REPORT / 'manifest-before-fixed-channels.json').write_bytes(encode(prior_manifest))
    (OUTPUT / 'manifest.json').write_bytes(encode(manifest))
    # Retire only previously generated, hash-verified public replay assets.
    # Never touch recordings or model files.
    current_files = {a['file'] for s in sessions for a in s['replays'].values()}
    for s in prior_manifest.get('sessions', []):
        for a in s['replays'].values():
            p = OUTPUT / a['file']
            if a['file'] not in current_files and p.parent == OUTPUT and p.is_file() and digest(p) == a['sha256']:
                p.unlink()
    (REPORT / 'sources.json').write_bytes(encode(sources))
    (REPORT / 'validation.json').write_bytes(encode({'source_fingerprint': source_fingerprint,
        'models_retrained': False, 'total_predictions': sum(v['trials'] for v in validations),
        'conditions': validations}))
    print(f'Export validated: {len(validations)} configurations, {sum(v["trials"] for v in validations)} predictions.')


if __name__ == '__main__':
    main()
