"""Move only the reviewed legacy paths, with checksums and rollback; never delete.

Run only after API and browser evidence is present. Raw EEG, common_model,
historical Handover documents and website visual assets remain in place.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

REPO=Path(__file__).resolve().parent.parent
EVIDENCE=REPO/'backend/local_cache/migration'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');args=p.parse_args()
    plan=json.loads((EVIDENCE/'plan.json').read_text());backup=Path(plan['backup_root'])
    git_root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=REPO,text=True).strip())
    assert not backup.is_relative_to(git_root)
    if not args.execute:
        print(json.dumps({e['source']:e['file_count'] for e in plan['targets']},indent=2));return
    for name in ['api_validation.json','browser_validation.json']:
        assert json.loads((EVIDENCE/name).read_text())['passed'],name
    for filename,expected in plan['protected'].items():assert sha(Path(filename))==expected,filename
    for filename,expected in plan['new_models'].items():assert sha(REPO/filename)==expected,filename
    for entry in plan['targets']:
        assert Path(entry['destination'])==backup/entry['source']
        assert not Path(entry['destination']).exists()
        for filename,expected in entry['files'].items():assert sha(REPO/filename)==expected,filename
    backup.mkdir(parents=True,exist_ok=False)
    moved=[]
    try:
        for entry in plan['targets']:
            source=REPO/entry['source'];dest=Path(entry['destination'])
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.move(str(source),str(dest));moved.append(entry)
            for filename,expected in entry['files'].items():assert sha(backup/filename)==expected,filename
        for filename,expected in plan['protected'].items():assert sha(Path(filename))==expected,filename
    except BaseException:
        for entry in reversed(moved):
            source=REPO/entry['source'];dest=Path(entry['destination'])
            if not source.exists():shutil.move(str(dest),str(source))
        raise
    plan.update(status='moved_and_hash_verified',moved_path_count=len(moved),
                moved_file_count=sum(e['file_count'] for e in moved),raw_data_deleted=False,
                git_root=str(git_root),api_evidence='backend/local_cache/migration/api_validation.json',
                browser_evidence='backend/local_cache/migration/browser_validation.json')
    manifest=json.dumps(plan,ensure_ascii=False,indent=2)
    (backup/'MIGRATION_MANIFEST.json').write_text(manifest)
    (EVIDENCE/'completed.json').write_text(manifest)
    (backup/'RESTORE.md').write_text(
        '# Legacy research backup\n\n'
        f'Original repository: `{REPO}`\n\n'
        'Every path under website/ keeps its original repository-relative location. '
        'MIGRATION_MANIFEST.json contains every source/destination and SHA256. '
        'Nothing was deleted. Original online EEG and common_model remain at their original paths.\n\n'
        'To restore: stop any legacy research task, check that each original target is absent, '
        'then move the corresponding backup path to its original repository path. '
        'Do not overwrite an existing path. Restore the old backend, models and source scripts '
        'together if reproducing that old environment; do not add them to the new backend runtime.\n'
    )
    print('MOVED',len(moved),'paths,',plan['moved_file_count'],'files; all checksums verified;',backup)


if __name__=='__main__':main()
