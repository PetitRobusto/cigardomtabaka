#!/usr/bin/env python3
"""
批量下载小雪茄图片并创建 CigarImage 记录
"""
import os, sys, json, django, hashlib, urllib.request, shutil

os.environ['DJANGO_SETTINGS_MODULE'] = 'moscow_cigar_backend.settings'
os.environ['DJANGO_DEBUG'] = 'True'
sys.path.insert(0, '/home/jason/moscow_cigar')
django.setup()

from django.core.files import File
from cigars.models import Cigar, CigarImage

MEDIA_ROOT = '/home/jason/moscow_cigar/media'
DATA_FILE = '/home/jason/moscow_cigar/timecigar_minis_full.json'

def slugify(text):
    """简单slug"""
    return text.lower().replace(' ', '-').replace('/', '-').replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n')

def download_image(url, save_path):
    """下载图片到本地"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, 'wb') as f:
                shutil.copyfileobj(resp, f)
        return True
    except Exception as e:
        print(f"    ❌ Download failed: {e}")
        return False

def main():
    # 加载产品数据
    with open(DATA_FILE) as f:
        products = json.load(f)
    
    img_map = {p['product_id']: p.get('primary_img', '') for p in products}
    
    # 获取所有机制茄
    cigars = Cigar.objects.filter(production_method='machine_rolled_short_filler')
    
    downloaded = 0
    skipped = 0
    errors = 0
    
    for cigar in cigars:
        # 从url提取product_id
        url = cigar.url or ''
        pid = None
        if 'product_id=' in url:
            pid = url.split('product_id=')[-1].split('&')[0]
        
        if not pid:
            continue
        
        img_url = img_map.get(pid, '')
        if not img_url:
            continue
        
        # 检查是否已有图片
        if CigarImage.objects.filter(cigar=cigar).exists():
            skipped += 1
            continue
        
        # 构建存储路径
        brand_slug = slugify(cigar.brand)
        name_slug = slugify(cigar.english_name or cigar.name or 'unknown')
        # 提取文件扩展名
        ext = os.path.splitext(img_url.split('?')[0])[1]
        if not ext or len(ext) > 5:
            ext = '.jpg'
        
        filename = f"{brand_slug}-{name_slug}{ext}"[:100]
        rel_dir = f"cigars/{brand_slug}/{name_slug}"
        abs_dir = os.path.join(MEDIA_ROOT, rel_dir)
        abs_path = os.path.join(abs_dir, filename)
        
        # 下载
        print(f"  [{cigar.brand}] {cigar.english_name[:30]}...")
        if download_image(img_url, abs_path):
            # 创建 CigarImage 记录
            rel_path = f"{rel_dir}/{filename}"
            try:
                img = CigarImage.objects.create(
                    cigar=cigar,
                    image=rel_path,
                    image_type='cigar',
                    is_primary=True,
                )
                downloaded += 1
                print(f"    ✅ {rel_path}")
            except Exception as e:
                errors += 1
                print(f"    ❌ DB error: {e}")
        else:
            errors += 1
    
    print(f"\n=== 完成: 下载 {downloaded} | 跳过 {skipped} | 错误 {errors} ===")

if __name__ == '__main__':
    main()
