import os,json,hashlib,pathlib
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.conf import settings
from apps.catalog.models import BannerMedia
from apps.catalog.utils.r2_utils import get_r2_client,get_r2_path
from botocore.exceptions import ClientError
folder=pathlib.Path('/tmp/mudaroba-banners-20260913')
manifest=json.loads((folder/'manifest.json').read_text())
client=get_r2_client()
bucket=settings.R2_CONFIG['bucket_name']
for item in manifest:
    assert item['replace']
    row=BannerMedia.objects.get(pk=item['id'])
    assert row.image.name==item['oldKey'], f"Image changed: {item['id']}"
    assert row.content_type=='image'
    assert client.head_object(Bucket=bucket,Key=get_r2_path(item['oldKey']))['ContentLength']==item['oldBytes']
    payload=(folder/item['filename']).read_bytes()
    assert hashlib.sha256(payload).hexdigest()==item['sha256']
    key=get_r2_path(item['newKey'])
    try:
        client.head_object(Bucket=bucket,Key=key)
    except ClientError as error:
        if error.response['Error']['Code'] not in ('404','NoSuchKey','NotFound'): raise
    else:
        raise RuntimeError(f'New key already exists: {key}')
    client.put_object(Bucket=bucket,Key=key,Body=payload,ContentType='image/webp',CacheControl='public, max-age=31536000, immutable',IfNoneMatch='*')
    head=client.head_object(Bucket=bucket,Key=key)
    assert head['ContentLength']==len(payload) and head['ContentType']=='image/webp'
    print(json.dumps({'uploaded':item['id'],'bytes':len(payload),'key':key}),flush=True)
