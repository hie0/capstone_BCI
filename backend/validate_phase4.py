"""Incremental Phase4 checks; reuse prior full validation and test newly exposed low mode.

Two processes verify independent participants; each trial stream stays chronological.
No fitting, no joblib writes, no original data writes. Logs stay in ignored cache.
"""
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import backend  # configure BLAS thread bounds before NumPy imports
import httpx
import joblib
import numpy as np
from threadpoolctl import threadpool_info, threadpool_limits
from backend.recorded_data import _load_session
from backend.research_protocol import StatefulOnlineTTASession


@lru_cache(maxsize=1)
def models():
    return joblib.load(ROOT / 'backend/models/online_50sessions_calib_models.joblib')


def check_subject(task):
    subject, session, data_root = task
    with threadpool_limits(limits=1):
        path = next((Path(data_root)/subject/session).glob('*_calibration_trial_log.csv'))
        _, data, _ = _load_session(path)
        entry = next(e for e in models().values() if e['subject']==subject and e['session']==session)
        rows=[]
        with httpx.Client(base_url='http://127.0.0.1:8000', timeout=60) as client:
            for tta in (False, True):
                model=entry['models'][f'low__tta_{"on" if tta else "off"}']
                engine=StatefulOnlineTTASession(model, tta_override=tta)
                for i in range(3):
                    local=engine.step(data['on']['bands'][model.band_name][i],
                        eog_ptp_uv=float(data['on']['eog'][i]),true_label_int=int(data['on']['y'][i]),
                        trial_id=i+1,timestamp_s=float(data['on']['timestamps'][i]),is_band_filtered=True)
                    r=client.post('/api/predict',json=dict(participant_id=subject,session_id=session,
                        channel_mode='low',tta_enabled=tta,trial_index=i,include_waveform=True))
                    r.raise_for_status();remote=r.json()
                    assert remote['active_channels']==model.active_channels
                    for field in ('decision_score','probability_right','raw_logit','calibrated_logit'):
                        assert np.isclose(local[field],remote[field],rtol=1e-10,atol=1e-10),(subject,field)
                    assert remote['latency_ms']>=0 and remote['waveform']
                    assert remote['quality']==local['quality']
                rows.append(dict(subject=subject,session=session,tta=tta,channel_mode='low',
                    montage=model.montage_name,active_channels=model.active_channels,checked_trials=3,passed=True))
        return dict(checks=rows,blas_threads=[p['num_threads'] for p in threadpool_info()])


def main():
    out=ROOT/'backend/local_cache/phase4';out.mkdir(parents=True,exist_ok=True)
    previous=json.loads((ROOT/'backend/local_cache/migration/api_validation.json').read_text())
    assert previous['passed']
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=60) as client:
        health=client.get('/api/health').json()
        assert health['models_loaded'] and health['local_eeg_sessions_cached']==12
        assert health['local_eeg_online_trials']==540
        sessions=client.get('/api/sessions').json()['sessions']
    tasks=[(p,(next(s for s in sessions if s['participant_id']==p))['session_id'],health['data_root'])
           for p in ('WMJ','KGE','OYJ','KHY')]
    with ProcessPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(check_subject,tasks))
    report=dict(passed=True,workers=2,blas_limit=1,trial_order='sequential within participant/config',
        health=health,results=results,reused_validation='backend/local_cache/migration/api_validation.json',
        model_training=False)
    (out/'api_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('PASS: health12/540, 4 participants x low TTA OFF/ON x3 chronological trials; direct-joblib/API parity; workers2/BLAS1')


if __name__=='__main__':
    main()
