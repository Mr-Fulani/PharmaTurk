import os,json,pathlib,sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.db import transaction
from django.core.serializers.json import DjangoJSONEncoder
from apps.catalog.models import BannerMedia
folder=pathlib.Path('/tmp/mudaroba-banners-20260913')
manifest=json.loads((folder/'manifest.json').read_text())
backup=json.loads((folder/'database-before.json').read_text())
rollback='--rollback' in sys.argv
with transaction.atomic():
    rows={row.pk:row for row in BannerMedia.objects.select_for_update().filter(pk__in=[x['id'] for x in manifest])}
    assert len(rows)==len(manifest)
    for item in manifest:
        oldkey,newkey=(item['newKey'],item['oldKey']) if rollback else (item['oldKey'],item['newKey'])
        row=rows[item['id']]
        assert row.image.name==oldkey, f"Concurrent image edit: {item['id']}"
        assert row.content_type=='image'
        if not rollback:
            current=BannerMedia.objects.filter(pk=row.pk).values().get()
            before=next(x for x in backup['media'] if x['id']==row.pk)
            assert json.loads(json.dumps(current,cls=DjangoJSONEncoder))==before, f"Concurrent record edit: {row.pk}"
        # Update only the image reference; retain originals and every other field.
        assert BannerMedia.objects.filter(pk=row.pk,image=oldkey).update(image=newkey)==1
print(json.dumps({'action':'rollback' if rollback else 'replace','rows':len(manifest)}))
