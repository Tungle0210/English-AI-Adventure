"""Minimal real S3 probes confined to a unique QA prefix. No production migration."""
import hashlib,json,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend import config

def client(unsigned=False):
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config
    kwargs={'region_name':config.setting('AWS_REGION'),'endpoint_url':config.setting('S3_ENDPOINT_URL') or None,
        'config':Config(signature_version=UNSIGNED if unsigned else 's3v4',s3={'addressing_style':'path'},connect_timeout=8,read_timeout=90,retries={'total_max_attempts':1},request_checksum_calculation='when_required',response_checksum_validation='when_required')}
    if not unsigned:kwargs.update(aws_access_key_id=config.setting('AWS_ACCESS_KEY_ID'),aws_secret_access_key=config.setting('AWS_SECRET_ACCESS_KEY'),aws_session_token=config.setting('AWS_SESSION_TOKEN') or None)
    return boto3.client('s3',**kwargs)

def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def probe():
    needed=['AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_REGION','S3_BUCKET','S3_ENDPOINT_URL']
    if not all(config.configured(config.setting(k)) for k in needed):return {'status':'NOT_TESTED','reason':'MISSING_CONFIG'}
    c=client();bucket=config.setting('S3_BUCKET');prefix='qa-eaa-'+uuid.uuid4().hex+'/'
    result={'qa_namespace_only':True,'existing_objects_modified':False,'tests':[]};created=[]
    try:
        start=time.perf_counter();c.head_bucket(Bucket=bucket)
        objects=c.list_objects_v2(Bucket=bucket,MaxKeys=1000)
        visible_bytes=sum(o['Size'] for o in objects.get('Contents',[]))
        result['visible_bucket_bytes']=visible_bytes;result['inventory_complete']=not objects.get('IsTruncated',False)
        small=b'English AI Adventure isolated connection probe\n'*20
        key=prefix+'small.txt';sha=hashlib.sha256(small).hexdigest();created.append(key)
        c.put_object(Bucket=bucket,Key=key,Body=small,Metadata={'sha256':sha},ContentType='text/plain')
        response=c.get_object(Bucket=bucket,Key=key)
        with response['Body'] as body:download=body.read()
        assert hashlib.sha256(download).hexdigest()==sha
        private=False
        try:
            anonymous=client(True).get_object(Bucket=bucket,Key=key,Range='bytes=0-0')
            anonymous['Body'].close()
        except Exception as e:private=getattr(e,'response',{}).get('ResponseMetadata',{}).get('HTTPStatusCode') in (401,403,404)
        assert private
        result['tests'].append({'name':'small','status':'PASS','bytes':len(small),'sha256_match':True,'anonymous_read_denied':True,'ms':round((time.perf_counter()-start)*1000,2)})
        path=ROOT/'input/Unit 6 Lesson 2 Period 3.pptx'
        neon_endpoint='.neon.tech' in config.setting('S3_ENDPOINT_URL')
        if not path.exists() or not neon_endpoint or objects.get('IsTruncated') or visible_bytes+path.stat().st_size>4_500_000_000:
            result['tests'].append({'name':'real_pptx','status':'NOT_TESTED','reason':'FREE_STORAGE_HEADROOM_NOT_ESTABLISHED'})
        else:
            from boto3.s3.transfer import TransferConfig
            start=time.perf_counter();key=prefix+'large.pptx';sha=digest(path);created.append(key)
            c.upload_file(str(path),bucket,key,ExtraArgs={'Metadata':{'sha256':sha},'ContentType':'application/vnd.openxmlformats-officedocument.presentationml.presentation'},Config=TransferConfig(multipart_threshold=8*1024*1024,multipart_chunksize=8*1024*1024,max_concurrency=1,use_threads=False))
            upload_ms=round((time.perf_counter()-start)*1000,2);start=time.perf_counter()
            response=c.get_object(Bucket=bucket,Key=key);h=hashlib.sha256();size=0
            with response['Body'] as body:
                for chunk in iter(lambda:body.read(1024*1024),b''):h.update(chunk);size+=len(chunk)
            assert size==path.stat().st_size and h.hexdigest()==sha
            result['tests'].append({'name':'real_pptx','status':'PASS','bytes':size,'sha256_match':True,'upload_ms':upload_ms,'download_ms':round((time.perf_counter()-start)*1000,2),'transfer_concurrency':1,'read_chunk_bytes':1024*1024,'scope':'S3 API from local host, not Render/Netlify'})
        result['status']='PASS' if all(t['status']=='PASS' for t in result['tests']) else 'PARTIAL'
    except Exception as e:
        code=getattr(e,'response',{}).get('Error',{}).get('Code')
        allowed={'AccessDenied','InvalidAccessKeyId','SignatureDoesNotMatch','NoSuchBucket','NoSuchKey','SlowDown','InvalidRequest','NotImplemented','403','404','500','503'}
        result.update(status='FAIL',error_type=type(e).__name__,error_code=code if code in allowed else None)
    finally:
        cleanup=[]
        for key in created:
            try:c.delete_object(Bucket=bucket,Key=key);cleanup.append(True)
            except Exception:cleanup.append(False)
        result['qa_objects_cleanup']='PASS' if all(cleanup) else 'FAIL'
        result['qa_objects_created']=len(created)
        if not all(cleanup):result['qa_prefix_for_manual_cleanup']=prefix
    return result

if __name__=='__main__':
    result=probe();(ROOT/'reports/neon/s3-probe.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
