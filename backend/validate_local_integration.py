"""Actual HTTP/WebSocket/recorded EEG integration checks; no training or legacy imports."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import httpx
import numpy as np
import pandas as pd
import websockets

from backend.recorded_data import load_recorded_sessions
from backend.research_protocol import resolve_data_root, CH_COLS


async def main():
    results=[]
    raw,diagnostics=load_recorded_sessions(resolve_data_root())
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',timeout=60.) as client:
        health=(await client.get('/api/health')).json()
        assert health['models_loaded'] and len(health['exported_joblib_files'])==5
        assert health['local_eeg_sessions_cached']==12 and health['local_eeg_online_trials']==540
        sessions=(await client.get('/api/sessions')).json()['sessions']
        assert len(sessions)==12
        for session in sessions:
            subject=session['participant_id'];name=session['session_id']
            mode='7ch' if subject in ['WMJ','KHY'] else '5ch'
            expected=raw[f'{subject}__{name}']
            for ch in ['16ch',mode]:
                for tta in [False,True]:
                    config=dict(participant_id=subject,session_id=name,channel_mode=ch,tta_enabled=tta)
                    init=await client.post('/api/session/init',json=config);assert init.status_code==200,init.text
                    response=await client.post('/api/evaluate/session',json=config)
                    assert response.status_code==200,response.text
                    data=response.json();preds=data['predictions']
                    assert data['total_trials']==len(expected['on']['y'])
                    assert data['n_channels']==int(ch[:-2])
                    for i,p in enumerate(preds):
                        assert p['trial_id']==i+1 and p['session_id']==name and p['participant_id']==subject
                        assert p['tta_state']['accumulated_trials']==i+1
                        assert p['true_direction']==('RIGHT' if expected['on']['y'][i] else 'LEFT')
                        assert np.isfinite(p['raw_logit']) and 0<=p['probability_right']<=1
                    for index in [0,2,0]:
                        p=await client.post('/api/predict',json=dict(config,trial_index=index,include_waveform=True))
                        assert p.status_code==200,p.text
                        item=p.json()
                        assert item['trial_id']==index+1 and item['waveform']
                        assert item['probability_right']==preds[index]['probability_right']
                    results.append(dict(subject=subject,session=name,channel=ch,tta=tta,trials=len(preds),passed=True))
        # Raw tensor path and diagnostic-label independence, using measured EEG (not random arrays).
        sample=sessions[0];subject=sample['participant_id'];name=sample['session_id']
        directory=Path(next(d['source_directory'] for d in diagnostics if d['subject']==subject and d['session']==name))
        log=pd.read_csv(next(directory.glob('*_online_trial_log.csv')))
        onset=int(log.iloc[0].classification_onset_stream_sample)
        raw_window=pd.read_csv(next(directory.glob('*_ExG.csv')),usecols=CH_COLS).iloc[onset:onset+500].to_numpy(float).T
        cfg=dict(participant_id=subject,session_id=name,channel_mode='5ch',tta_enabled=True,
                 eeg_data=raw_window.tolist(),is_band_filtered=False,reset_session_state=True)
        left=(await client.post('/api/predict',json=dict(cfg,true_direction='LEFT'))).json()
        right=(await client.post('/api/predict',json=dict(cfg,true_direction='RIGHT'))).json()
        assert left['probability_right']==right['probability_right']
        replay=await client.get('/api/replay',params={k:cfg[k] for k in ['participant_id','session_id','channel_mode','tta_enabled']})
        assert replay.status_code==200,replay.text
        source=replay.json()['replay_source'];assert source['kind']=='recorded' and source['frames']
        for bad in ['missing-session','session-99']:
            r=await client.post('/api/predict',json=dict(participant_id=subject,session_id=bad))
            assert r.status_code==400,r.text
    ws_results=[]
    for subject in ['WMJ','KGE','OYJ','KHY']:
        session=next(s for s in sessions if s['participant_id']==subject)
        async with websockets.connect('ws://127.0.0.1:8000/ws/eeg') as ws:
            assert json.loads(await ws.recv())['type']=='connected'
            await ws.send(json.dumps(dict(action='set_config',participant_id=subject,session_id=session['session_id'],
                                        channel_mode='7ch' if subject in ['WMJ','KHY'] else '5ch',tta_enabled=True)))
            assert json.loads(await ws.recv())['type']=='config_ack'
            for index in [0,1,0]:
                await ws.send(json.dumps(dict(action='step_trial',trial_index=index,include_waveform=True)))
                msg=json.loads(await ws.recv());assert msg['type']=='trial_prediction',msg
                p=msg['prediction'];assert p['trial_id']==index+1 and p['participant_id']==subject and p['waveform']
            ws_results.append(dict(subject=subject,passed=True,actual_EEG=True))
    # Two clients must have independent causal trial counters.
    async with websockets.connect('ws://127.0.0.1:8000/ws/eeg') as a, websockets.connect('ws://127.0.0.1:8000/ws/eeg') as b:
        await a.recv();await b.recv()
        await a.send('{"action":"step_trial"}');pa=json.loads(await a.recv())['prediction']
        await a.send('{"action":"step_trial"}');await a.recv()
        await b.send('{"action":"step_trial"}');pb=json.loads(await b.recv())['prediction']
        assert pa['probability_right']==pb['probability_right'] and pb['step_index']==1
    out=Path(__file__).resolve().parent/'local_cache/migration'
    out.mkdir(parents=True,exist_ok=True)
    report=dict(passed=True,health=health,REST_session_evaluations=results,
        evaluated_trial_conditions=sum(r['trials'] for r in results),websocket_participants=ws_results,
        client_state_isolation=True,unknown_session_rejected=True,diagnostic_label_invariance=True,
        actual_raw_EEG_tensor_test=True,replay_source_verified=True,data_diagnostics=diagnostics)
    (out/'api_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('PASS:48 actual session evaluations /2160 trial conditions,4 WebSocket participants,raw EEG,replay,state isolation')


if __name__=='__main__':asyncio.run(main())
