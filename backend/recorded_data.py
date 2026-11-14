"""Local read-only CSV adapter; no legacy backend, model exports or research scripts.

Keeps the research-backend export's continuous filters and logged sample indices.
Marker alignment, metadata, MI duration, labels and complete epochs are validated.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
from scipy.signal import sosfilt

from backend.research_protocol import FS,CH_COLS,IDX_EOG,SOS_NOTCH,ONLINE_BAND_SOS


def load_recorded_sessions(root: Path) -> tuple[dict, list[dict]]:
    if not root.is_dir():
        raise FileNotFoundError(f'BCI_DATA_ROOT is not a directory: {root}')
    paths=sorted(root.rglob('*_calibration_trial_log.csv'))
    if not paths:raise ValueError(f'No recorded sessions under BCI_DATA_ROOT={root}')
    # Independent sessions only; chronological filtering within each stays unchanged.
    # Two concurrent CSV reads bound peak memory on the local 8GiB Mac.
    with ThreadPoolExecutor(max_workers=2) as pool:
        loaded=list(pool.map(_load_session,paths))
    return ({key:data for key,data,_ in loaded},[d for _,_,d in loaded])


def _load_session(calibration_path: Path):
    folder=calibration_path.parent
    files={}
    for kind in ['ExG','Marker','Meta','calibration_trial_log','online_trial_log','calibration_summary','ORN']:
        matches=list(folder.glob(f'*_{kind}.csv'))
        if len(matches)!=1:raise ValueError(f'{folder.name}: expected one {kind}')
        files[kind]=matches[0]
    meta=pd.read_csv(files['Meta']).iloc[0]
    if float(meta.sr)!=FS or meta.ExGUnits!='uV':raise ValueError(f'{folder.name}: expected250Hz/uV')
    cal=pd.read_csv(files['calibration_trial_log']);online=pd.read_csv(files['online_trial_log'])
    subjects=set(cal.subject.str.upper())|set(online.subject.str.upper())
    if len(subjects)!=1:raise ValueError(f'{folder.name}: mixed subjects')
    subject=subjects.pop()
    if subject not in ['WMJ','KGE','OYJ','KHY']:raise ValueError(subject)
    if len(cal)!=20 or cal.target_direction.value_counts().to_dict()!={'LEFT':10,'RIGHT':10}:
        raise ValueError(f'{folder.name}: expected20 balanced calibration trials')
    raw=pd.read_csv(files['ExG']);x=raw[CH_COLS].to_numpy(np.float64)
    ts=raw.TimeStamp.to_numpy(float)
    for i in np.flatnonzero(np.diff(ts)<0):ts[i+1:]+=ts[i]+1/FS-ts[i+1]
    markers=pd.read_csv(files['Marker']);codes=markers.Code.astype(str).str.extract(r'(\d+)')[0].astype(int)
    cues=markers.loc[codes.isin([12,13])];onsets=markers.loc[codes==33]
    if len(cues)!=len(cal) or len(onsets)!=len(online):raise ValueError(f'{folder.name}: Marker/log count mismatch')
    if not np.array_equal(codes.loc[cues.index],np.where(cal.target_direction=='LEFT',12,13)):
        raise ValueError(f'{folder.name}: calibration marker labels differ')
    notched=sosfilt(SOS_NOTCH,x,axis=0)
    bands={k:sosfilt(s,notched,axis=0) for k,s in ONLINE_BAND_SOS.items()}
    alignment={}
    def parse(log,is_cal):
        column='calibration_cue_stream_sample' if is_cal else 'classification_onset_stream_sample'
        samples=log[column].to_numpy(int)
        marker_times=cues.TimeStamp.to_numpy(float) if is_cal else onsets.TimeStamp.to_numpy(float)
        delta=np.searchsorted(ts,marker_times)-samples
        if np.max(np.abs(delta))>50:raise ValueError(f'{folder.name}: marker/log delta>50samples')
        if np.any(samples<0) or np.any(samples+500>len(x)) or np.any(np.diff(samples)<=0):
            raise ValueError(f'{folder.name}: incomplete/nonchronological EEG epochs')
        if not is_cal and (log.decision_time_s<2).any():
            raise ValueError(f'{folder.name}: insufficient MI for fixed2s export epoch')
        alignment['calibration' if is_cal else 'online']=delta.tolist()
        return dict(bands={k:np.stack([a[i:i+500].T.astype(np.float32) for i in samples]) for k,a in bands.items()},
            y=np.where(log.target_direction.to_numpy()=='LEFT',0,1).astype(np.int64),
            eog=np.array([np.max(np.ptp(notched[i:i+375,IDX_EOG],axis=0)) for i in samples]),
            timestamps=samples.astype(float)/FS,
            live_acc=float(log.is_correct.mean()*100) if not is_cal else float('nan'),
            dur=float(log.decision_time_s.median()) if not is_cal else 3.)
    key=f'{subject}__{folder.name}'
    data=dict(subject=subject,session=folder.name,cal=parse(cal,True),on=parse(online,False))
    diagnostic=dict(subject=subject,session=folder.name,online_trials=len(online),calibration_trials=len(cal),
        source_directory=str(folder),alignment=alignment,filtering='continuous causal notch60Hz +4th-order bandpass',
        onset='original export logged sample indices; independently checked against Marker12/13/33 within50samples')
    return key,data,diagnostic
