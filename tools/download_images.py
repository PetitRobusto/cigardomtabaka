#!/usr/bin/env python3
"""
CDP-based image downloader v3 — pre-loads all Cigar→path mappings synchronously,
then downloads images via browser fetch() to bypass Cloudflare.
"""
import asyncio, json, os, sys, time, base64, re
from pathlib import Path
import urllib.request
import websockets
from PIL import Image

# Django setup (sync)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'moscow_cigar_backend.settings')
import django
django.setup()
from cigars.models import Cigar, CigarImage
from django.utils.text import slugify

MANIFEST = PROJECT_ROOT / 'image_manifest.json'
MEDIA_ROOT = PROJECT_ROOT / 'media'
THUMB_SIZE = (300, 300)
CDP_PORT = 9222

print("Loading manifest + building cigar index...")
with open(MANIFEST) as f:
    entries = json.load(f)

# ---- SYNC: Build download job list ----
jobs = []  # [(url, save_path, thumb_path, img_type, is_primary)]
for entry in entries:
    brand = entry['brand']
    status = entry['status']
    rt = entry.get('release_type', '')
    # Clean sub_names: strip whitespace, remove trailing count annotations like "(50)"
    sub_names_raw = [s.strip() for s in entry.get('sub_names', [])]
    sub_names = [re.sub(r'\s*\(\d+\)\s*$', '', s).strip() for s in sub_names_raw]
    brand_slug = slugify(brand)
    images = entry.get('images', [])

    # Find matching cigars
    if status == 'Special Releases' and rt:
        cigars = list(Cigar.objects.filter(brand=brand, release_type=rt, status='Special Releases'))
        cigars = [c for c in cigars if c.english_name in sub_names] or cigars
    elif sub_names:
        c = Cigar.objects.filter(brand=brand, english_name=sub_names[0], release_type='').first()
        if not c:
            c = Cigar.objects.filter(brand=brand, english_name__in=sub_names).first()
        cigars = [c] if c else []
    else:
        cigars = []

    if not cigars:
        continue

    primary_type = 'special' if entry.get('dh_count', 1) > 1 else 'cigar'

    for img_data in images:
        url = img_data['url']
        img_type = img_data['type']

        # Match to specific cigar for multi-cigar releases
        target = cigars[0]
        if len(cigars) > 1 and img_type == 'cigar':
            fname = Path(img_data['path']).stem.lower().replace('-', ' ')
            for i, sn in enumerate(sub_names):
                sn_slug = sn.lower().replace(' ', '-')
                if sn_slug in fname or sn.lower() in fname:
                    if i < len(cigars):
                        target = cigars[i]
                    break

        name_slug = slugify(target.english_name)
        if target.release_type:
            name_slug += '-' + slugify(target.release_type)
        dir_path = MEDIA_ROOT / 'cigars' / brand_slug / name_slug
        # Always include type in filename to avoid cigar/band/packaging collisions
        stem = Path(img_data['path']).stem
        suffix = Path(img_data['path']).suffix
        fname = f"{stem}-{img_type}{suffix}"
        save_path = dir_path / fname
        thumb_path = dir_path / 'thumbnails' / fname

        # Check primary
        has_primary = CigarImage.objects.filter(cigar=target, is_primary=True).exists()
        is_primary = (img_type == primary_type and not has_primary)

        jobs.append({
            'url': url,
            'save_path': save_path,
            'thumb_path': thumb_path,
            'cigar_id': target.pk,
            'img_type': img_type,
            'is_primary': is_primary,
        })

print(f"Jobs: {len(jobs)} images to process")
print(f"Media root: {MEDIA_ROOT}")
print()

# Filter out already-existing files, but keep original list for DB补录
all_jobs = jobs[:]  # save full list before filtering
new_jobs = []
skipped = 0
for j in jobs:
    if j['save_path'].exists():
        skipped += 1
    else:
        new_jobs.append(j)
print(f"Skipping {skipped} existing, {len(new_jobs)} to download")
jobs = new_jobs

if not jobs:
    print("Nothing to download!")

def ensure_db_records(job_list):
    """Create CigarImage records for all jobs whose files exist on disk.
    Uses (cigar_id, image_url, image_type) as unique key to avoid collisions
    when multiple images share the same cigar."""
    created = 0
    for j in job_list:
        if not j['save_path'].exists():
            continue
        rel_img = str(j['save_path'].relative_to(MEDIA_ROOT))
        rel_thumb = str(j['thumb_path'].relative_to(MEDIA_ROOT)) if j['thumb_path'].exists() else ''
        CigarImage.objects.get_or_create(
            cigar_id=j['cigar_id'], image_url=j['url'], image_type=j['img_type'],
            defaults={'image': rel_img, 'thumbnail': rel_thumb,
                      'is_primary': j['is_primary']}
        )
        created += 1
    return created

if not jobs:
    existing = ensure_db_records(all_jobs)
    print(f"DB records ensured: {existing}")
    sys.exit(0)


# ---- ASYNC: Download via CDP browser fetch ----

def get_cdp():
    targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json").read())
    for t in targets:
        if t["type"] == "page":
            return t["webSocketDebuggerUrl"]
    return None


async def cdp_call(ws, method, params=None):
    cdp_call._id = getattr(cdp_call, '_id', 0) + 1
    await ws.send(json.dumps({"id": cdp_call._id, "method": method, "params": params or {}}))
    while True:
        resp = json.loads(await ws.recv())
        if resp.get("id") == cdp_call._id:
            return resp


def save_one(job, data_b64):
    """Save image + thumbnail + DB record (sync)."""
    job['save_path'].parent.mkdir(parents=True, exist_ok=True)
    data = base64.b64decode(data_b64)
    job['save_path'].write_bytes(data)

    # Thumbnail
    thumb_ok = False
    try:
        img = Image.open(job['save_path'])
        img.thumbnail(THUMB_SIZE, Image.LANCZOS)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        job['thumb_path'].parent.mkdir(parents=True, exist_ok=True)
        img.save(job['thumb_path'], 'JPEG', quality=85)
        thumb_ok = True
    except Exception:
        pass

    # DB
    rel_img = str(job['save_path'].relative_to(MEDIA_ROOT))
    rel_thumb = str(job['thumb_path'].relative_to(MEDIA_ROOT)) if job['thumb_path'].exists() else ''
    CigarImage.objects.get_or_create(
        cigar_id=job['cigar_id'], image_url=job['url'], image_type=job['img_type'],
        defaults={'image': rel_img, 'thumbnail': rel_thumb,
                  'is_primary': job['is_primary']}
    )
    return thumb_ok


async def download_batch(ws, batch):
    """Download one batch via browser fetch(). Return {url: b64data or None}."""
    urls = [j['url'] for j in batch]
    js = f"""
    (async () => {{
        const urls = {json.dumps(urls)};
        const results = {{}};
        await Promise.all(urls.map(async (url) => {{
            try {{
                const resp = await fetch(url);
                if (!resp.ok) {{ results[url] = {{error: resp.status}}; return; }}
                const buf = await resp.arrayBuffer();
                const bytes = new Uint8Array(buf);
                let binary = '';
                for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
                results[url] = {{data: btoa(binary)}};
            }} catch(e) {{
                results[url] = {{error: String(e)}};
            }}
        }}));
        return JSON.stringify(results);
    }})()
    """
    resp = await cdp_call(ws, "Runtime.evaluate", {
        "expression": js, "returnByValue": True,
        "awaitPromise": True, "timeout": 120000
    })
    raw = resp.get("result", {}).get("result", {}).get("value", "{}")
    return json.loads(raw)


async def main_async():
    cdp_url = get_cdp()
    if not cdp_url:
        print("ERROR: No CDP page!")
        return

    stats = {'dl': 0, 'fail': 0, 'thumb': 0, 'db': 0}
    total = len(jobs)
    BATCH = 8

    async with websockets.connect(cdp_url, max_size=200 * 1024 * 1024) as ws:
        for i in range(0, total, BATCH):
            batch = jobs[i:i + BATCH]
            results = await download_batch(ws, batch)

            for j in batch:
                result = results.get(j['url'], {})
                if 'error' in result:
                    stats['fail'] += 1
                    print(f"  ✗ {j['save_path'].name}: {result['error']}")
                else:
                    thumb_ok = await asyncio.get_event_loop().run_in_executor(
                        None, save_one, j, result['data']
                    )
                    stats['dl'] += 1
                    if thumb_ok:
                        stats['thumb'] += 1
                    stats['db'] += 1

            pct = min(100, int((i + BATCH) / total * 100))
            elapsed = time.time() - start_time
            rate = (stats['dl'] + stats['fail']) / elapsed * 60 if elapsed > 0 else 0
            print(f"  [{pct:3d}%] {i+BATCH}/{total} | dl:{stats['dl']} fail:{stats['fail']} thumb:{stats['thumb']} db:{stats['db']} | {rate:.0f}/min")

            await asyncio.sleep(1)

    print(f"\n{'='*50}")
    print(f"DONE!")
    for k, v in stats.items():
        print(f"  {k}: {v}")


start_time = time.time()
asyncio.run(main_async())
