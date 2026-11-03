"""Private, content-addressed baseline preservation; no remote archival upload."""
from hashlib import sha256
from pathlib import Path
import os
from .baseline import ARTIFACT_SHA256,ARTIFACT_ID
from .research import DataBlocked,write_once

def preserve(archive,root):
    archive=Path(archive);root=Path(root).resolve()
    if not root.name.startswith('v101_'):raise DataBlocked('INDEPENDENT_ARCHIVE_REQUIRED')
    if any(p.name in {'v10_forward_store','v10-original-readonly','.git'} for p in (root,*root.parents)):
        raise DataBlocked('ORIGINAL_STORE_IS_READ_ONLY')
    body=archive.read_bytes();digest=sha256(body).hexdigest()
    if digest!=ARTIFACT_SHA256:raise DataBlocked('ARCHIVE_DIGEST_CONTINUITY_FAILED')
    root.mkdir(parents=True,exist_ok=True);target=root/(digest+'.zip')
    if target.exists():
        if sha256(target.read_bytes()).hexdigest()!=digest:raise DataBlocked('ARCHIVED_BYTES_CHANGED')
    else:
        with target.open('xb') as f:f.write(body);f.flush();os.fsync(f.fileno())
    write_once(root/'manifest.json',dict(artifact_id=ARTIFACT_ID,sha256=digest,
        file=target.name,mode='LOCAL_PRIVATE_ARCHIVE',remote_archival_approved=False))
    return target
