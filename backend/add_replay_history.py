"""Attach measured pre-trial display history without repeating model inference.

Original recordings, fitted models and existing prediction fields are unchanged.
Retired generated assets are backed up privately before manifest replacement.
"""
import copy
import hashlib
import json

from backend.export_recorded_replay import OUTPUT, REPORT, digest, encode
from backend.inference_engine import MODELS_DIR, inference_manager as manager


def main():
    manager.load_all()
    source_hashes = {p.name: digest(p) for p in MODELS_DIR.glob('*.joblib')}
    manifest_path = OUTPUT / 'manifest.json'
    original_manifest = manifest_path.read_bytes()
    manifest = json.loads(original_manifest)
    backup = REPORT / 'before-history-prefill'
    backup.mkdir(parents=True, exist_ok=True)
    if not (backup / 'manifest.json').exists():
        (backup / 'manifest.json').write_bytes(original_manifest)
    retired, audit = [], []
    for session in manifest['sessions']:
        subject, sid = session['participant_id'], session['session_id']
        on = manager.raw_sessions_map[f'{subject}__{sid}']['on']
        for key, asset in session['replays'].items():
            old_path = OUTPUT / asset['file']
            old_bytes = old_path.read_bytes()
            assert hashlib.sha256(old_bytes).hexdigest() == asset['sha256']
            data = json.loads(old_bytes)
            original_predictions = copy.deepcopy(data['predictions'])
            channel, tta = key.split('__tta_')
            _, model = manager.resolve_calib_model(subject, sid, channel, tta == 'on')
            history = manager.extract_waveform_snippet(on['history_bands'][model.band_name], model.active_channels)
            assert set(history) == set(data['predictions'][0]['active_channels'])
            assert all(len(values) == 500 for values in history.values())
            data['predictions'][0]['history_waveform'] = history
            # Every inference result and existing display sample must remain exact.
            for old, new in zip(original_predictions, data['predictions']):
                old.pop('history_waveform', None)
                check = {k: v for k, v in new.items() if k != 'history_waveform'}
                assert old == check
            raw = encode(data)
            sha = hashlib.sha256(raw).hexdigest()
            filename = f'{sid}-{key}-{sha[:12]}.json'
            (OUTPUT / filename).write_bytes(raw)
            if filename != asset['file']:
                (backup / asset['file']).write_bytes(old_bytes)
                retired.append(old_path)
            session['replays'][key] = dict(file=filename, sha256=sha, bytes=len(raw))
            audit.append(dict(session=sid, configuration=key, history_samples=500,
                              existing_predictions_unchanged=True))
    manifest['waveform']['pre_trial_history_samples'] = 500
    manifest['waveform']['history_source'] = 'continuously filtered EEG immediately before first online epoch'
    manifest_path.write_bytes(encode(manifest))
    current_files = {a['file'] for s in manifest['sessions'] for a in s['replays'].values()}
    for path in retired:
        if path.name not in current_files:
            path.unlink()
    assert source_hashes == {p.name: digest(p) for p in MODELS_DIR.glob('*.joblib')}
    (REPORT / 'history-prefill-validation.json').write_bytes(encode(dict(
        inference_executed=False, models_retrained=False, model_sha256=source_hashes,
        source='1000 samples before first logged classification onset, causal continuous filtering, decimated to 125Hz',
        conditions=audit)))
    print(f'Attached measured pre-trial history to {len(audit)} configurations; predictions unchanged; no inference or training.')


if __name__ == '__main__':
    main()
