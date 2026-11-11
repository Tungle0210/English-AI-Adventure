"""Private S3 objects; local files are disposable cache, never the cloud source of truth."""
import hashlib,json,os,uuid
from pathlib import PurePosixPath
from . import config

class ObjectFailure(RuntimeError):pass

CLIENTS={}
def client():
    import boto3
    from botocore.config import Config
    values=tuple(config.setting(k) for k in ('AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN','AWS_REGION','S3_ENDPOINT_URL'))
    if not all(config.configured(v) for v in (values[0],values[1],values[3])):raise ObjectFailure('S3 credentials missing')
    if values not in CLIENTS:
        CLIENTS[values]=boto3.client('s3',aws_access_key_id=values[0],aws_secret_access_key=values[1],aws_session_token=values[2] or None,region_name=values[3],endpoint_url=values[4] or None,
            config=Config(signature_version='s3v4',s3={'addressing_style':'path'},connect_timeout=8,read_timeout=90,retries={'total_max_attempts':2},request_checksum_calculation='when_required',response_checksum_validation='when_required'))
    return CLIENTS[values]

def bucket():
    value=config.setting('S3_BUCKET')
    if not config.configured(value):raise ObjectFailure('S3 bucket missing')
    return value

def key(relative):
    p=PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or '\\' in relative or ':' in relative:raise ObjectFailure('Unsafe object path')
    prefix=config.setting('S3_PREFIX','english-ai-adventure').strip('/')
    if not prefix or '..' in prefix.split('/'):raise ObjectFailure('Invalid object namespace')
    return prefix+'/'+(str(p) if relative else '')

def checksum(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def head(relative):
    try:return client().head_object(Bucket=bucket(),Key=key(relative))
    except Exception as e:
        if getattr(e,'response',{}).get('ResponseMetadata',{}).get('HTTPStatusCode')==404:return None
        raise ObjectFailure('S3 metadata unavailable') from None

def publish(root,relative):
    if not config.object_storage():return
    from boto3.s3.transfer import TransferConfig
    path=root/relative
    try:
        client().upload_file(str(path),bucket(),key(relative),ExtraArgs={'Metadata':{'sha256':checksum(path)}},Config=TransferConfig(multipart_threshold=8*1024*1024,multipart_chunksize=8*1024*1024,max_concurrency=1,use_threads=False))
    except Exception:raise ObjectFailure('S3 upload failed; local source retained') from None

def ensure(root,relative,refresh=False):
    path=root/relative
    if not config.object_storage() or (path.exists() and not refresh):return path
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.fetch-'+uuid.uuid4().hex)
    try:
        response=client().get_object(Bucket=bucket(),Key=key(relative));h=hashlib.sha256()
        with response['Body'] as body,temp.open('wb') as f:
            for chunk in iter(lambda:body.read(1024*1024),b''):h.update(chunk);f.write(chunk)
        expected=response.get('Metadata',{}).get('sha256')
        if not expected or h.hexdigest()!=expected:raise ObjectFailure('S3 checksum mismatch')
        temp.replace(path);return path
    except Exception:raise ObjectFailure('S3 download or checksum failed') from None
    finally:temp.unlink(missing_ok=True)

def put_bytes(relative,body):
    sha=hashlib.sha256(body).hexdigest()
    try:client().put_object(Bucket=bucket(),Key=key(relative),Body=body,Metadata={'sha256':sha})
    except Exception:raise ObjectFailure('S3 chunk write failed') from None

def list_names(prefix):
    result=[]
    try:
        for page in client().get_paginator('list_objects_v2').paginate(Bucket=bucket(),Prefix=key(prefix)):
            for row in page.get('Contents',[]):result.append(row['Key'][len(config.setting('S3_PREFIX','english-ai-adventure').strip('/'))+1:])
    except Exception:raise ObjectFailure('S3 listing failed') from None
    return result

def delete_known_object(root,relative):
    """Remove a precisely identified retired object, never a bucket or wildcard."""
    # key() rejects absolute paths, traversal and empty keys.
    object_key=key(relative)
    local=root/relative
    if config.object_storage():
        try:
            present=bool(head(relative))
            if present:client().delete_object(Bucket=bucket(),Key=object_key)
        except Exception:raise ObjectFailure('S3 delete failed for retired object') from None
    else:
        present=local.is_file()
    if local.is_file():local.unlink()
    return present

def register_asset(root,document_hash,ident):
    if not config.object_storage():return
    relative='indexes/'+document_hash+'.json';path=root/relative
    if not path.exists() and head(relative):ensure(root,relative)
    items=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    if ident not in items:items.append(ident)
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(items),encoding='utf-8');publish(root,relative)

def load_asset_index(root,document_hash):
    if not config.object_storage():return
    relative='indexes/'+document_hash+'.json'
    if head(relative):
        for ident in json.loads(ensure(root,relative,refresh=True).read_text(encoding='utf-8')):
            if len(ident)==64 and all(c in '0123456789abcdef' for c in ident):ensure(root,'media/'+ident+'.json')

def materialize_upload(root,ident,size):
    path=root/'uploads'/(ident+'.part');path.parent.mkdir(parents=True,exist_ok=True)
    verified=path.with_suffix('.part.sha256')
    if path.exists() and path.stat().st_size==size and verified.exists() and checksum(path)==verified.read_text(encoding='ascii'):return path
    position=0
    legacy='uploads/'+ident+'.part'
    if head(legacy):
        ensure(root,legacy,refresh=True);position=path.stat().st_size
    else:path.write_bytes(b'')
    if position>size:raise ObjectFailure('Legacy upload exceeds declared size')
    with path.open('ab') as dest:
        while position<size:
            relative='upload-chunks/'+ident+'/'+str(position)
            response=client().get_object(Bucket=bucket(),Key=key(relative));data=response['Body'].read(2*1024*1024+1);response['Body'].close()
            if not data or len(data)>2*1024*1024 or position+len(data)>size or hashlib.sha256(data).hexdigest()!=response.get('Metadata',{}).get('sha256'):raise ObjectFailure('Upload chunk checksum/size mismatch')
            dest.write(data);position+=len(data)
    verified.write_text(checksum(path),encoding='ascii')
    return path
