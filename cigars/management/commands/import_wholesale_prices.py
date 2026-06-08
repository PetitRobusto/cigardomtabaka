import json
import os
import re
import unicodedata
from django.core.management.base import BaseCommand
from cigars.models import Cigar, CigarPrice


ACCENT_MAP = str.maketrans({
    'à': 'a', 'á': 'a', 'â': 'a', 'ã': 'a', 'ä': 'a', 'å': 'a',
    'è': 'e', 'é': 'e', 'ê': 'e', 'ë': 'e',
    'ì': 'i', 'í': 'i', 'î': 'i', 'ï': 'i',
    'ò': 'o', 'ó': 'o', 'ô': 'o', 'õ': 'o', 'ö': 'o',
    'ù': 'u', 'ú': 'u', 'û': 'u', 'ü': 'u',
    'ý': 'y', 'ÿ': 'y',
    'ñ': 'n',
    'ç': 'c',
    'À': 'A', 'Á': 'A', 'Â': 'A', 'Ã': 'A', 'Ä': 'A', 'Å': 'A',
    'È': 'E', 'É': 'E', 'Ê': 'E', 'Ë': 'E',
    'Ì': 'I', 'Í': 'I', 'Î': 'I', 'Ï': 'I',
    'Ò': 'O', 'Ó': 'O', 'Ô': 'O', 'Õ': 'O', 'Ö': 'O',
    'Ù': 'U', 'Ú': 'U', 'Û': 'U', 'Ü': 'U',
    'Ý': 'Y',
    'Ñ': 'N',
    'Ç': 'C',
})


# 设计稿品牌名 -> DB 品牌名 映射（处理大小写、重音符号差异）
BRAND_MAP = {
    'Cohiba': 'Cohiba',
    'Montecristo': 'Montecristo',
    'Romeo Y Julieta': 'Romeo y Julieta',
    'Partagas': 'Partagás',
    'Hoyo de Monterrey': 'Hoyo de Monterrey',
    'H. Upmann': 'H. Upmann',
    'Trinidad': 'Trinidad',
    "Quai D'Orsay": "Quai d'Orsay",
    'Vegueros': 'Vegueros',
    'Quintero': 'Quintero',
    'Jose L. Piedra': 'José L. Piedra',
    'Ramon Allones': 'Ramón Allones',
}


class Command(BaseCommand):
    help = '导入批发价数据到 CigarPrice 模型（通过 english_name 匹配 Cigar 记录）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default='',
            help='JSON 文件路径，包含 [{"english_name": "...", "box_size": 25, "wholesale_price": 10000, ...}]',
        )
        parser.add_argument(
            '--from-design',
            action='store_true',
            help='从 .opendesign/privnote-create.html 解析 quoteProducts 数据',
        )

    def handle(self, *args, **options):
        file_path = options['file']
        from_design = options['from_design']

        if from_design:
            data = self._parse_design_file()
        elif not file_path:
            self.stdout.write(self.style.WARNING('未提供数据文件，使用内置示例数据（仅用于测试）'))
            data = self._get_sample_data()
        else:
            if not os.path.exists(file_path):
                self.stdout.write(self.style.ERROR(f'文件不存在: {file_path}'))
                return
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

        matched = 0
        unmatched = []
        created_count = 0
        updated_count = 0

        for entry in data:
            ename = entry.get('english_name', '').strip()
            brand_hint = entry.get('brand', '').strip()
            box_size = entry.get('box_size')
            wholesale_price = entry.get('wholesale_price')
            retail_price = entry.get('retail_price')
            sort_order = entry.get('sort_order', 0)
            is_active = entry.get('is_active', True)

            if not ename or not box_size or not wholesale_price:
                self.stdout.write(self.style.WARNING(f'跳过无效记录: {entry}'))
                continue

            cigar = self._find_cigar(ename, brand_hint)

            if cigar:
                cp, created = CigarPrice.objects.update_or_create(
                    cigar=cigar,
                    box_size=box_size,
                    defaults={
                        'wholesale_price': wholesale_price,
                        'retail_price': retail_price,
                        'sort_order': sort_order,
                        'is_active': is_active,
                    }
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1
                self.stdout.write(f'{"创建" if created else "更新"}: {cigar.brand} · {cigar.english_name} · {box_size}支/盒 · ¥{wholesale_price}')
                matched += 1
            else:
                unmatched.append(ename)
                self.stdout.write(self.style.WARNING(f'未匹配: {ename}'))

        self.stdout.write(self.style.SUCCESS(
            f'\n导入完成：匹配 {matched} 款（新建 {created_count}，更新 {updated_count}），未匹配 {len(unmatched)} 款'
        ))
        if unmatched:
            self.stdout.write(self.style.WARNING(f'未匹配列表: {unmatched}'))

    # 设计稿名称中某些变体词 → DB english_name 中实际使用的词
    NAME_ALIAS_MAP = {
        'LINEA MAESTRA': 'Maestro',
        'LINEA MAESTRO': 'Maestro',
    }

    def _normalize_name(self, name: str) -> str:
        """标准化名称：去重音、去 5*5 后缀、去 No. 空格差异、替换别名"""
        n = name
        n = re.sub(r'\s*\d+[ *xX]\d+', '', n)
        n = n.translate(ACCENT_MAP)
        n = re.sub(r'\b(No\.)\s*(\d)', r'\1 \2', n)
        n = ' '.join(n.split())

        upper = n.upper()
        for alias, replacement in self.NAME_ALIAS_MAP.items():
            if alias in upper:
                n = upper.replace(alias, replacement.upper())
                break
        n = ' '.join(n.split())
        return n

    def _find_cigar(self, ename: str, brand_hint: str) -> Cigar | None:
        """多策略匹配雪茄记录"""
        # 策略0: 先用标准化名称尝试精确匹配
        normalized_ename = self._normalize_name(ename)

        # 策略1: 精确匹配（整个 name 作为 english_name）
        cigars = Cigar.objects.filter(english_name__iexact=ename)
        if cigars.exists():
            return cigars.first()
        if cigars.exists():
            return cigars.first()

        # 策略2: 去除多余空格后精确匹配
        normalized = ' '.join(ename.split())
        cigars = Cigar.objects.filter(english_name__iexact=normalized)
        if cigars.exists():
            return cigars.first()

        # 提取 DB 品牌名
        db_brand = None
        if brand_hint:
            # brand_hint 格式: "高希霸 Cohiba" -> 取英文部分
            parts = brand_hint.split()
            if len(parts) >= 2:
                brand_en = ' '.join(parts[1:])
                db_brand = BRAND_MAP.get(brand_en, brand_en)

        if db_brand:
            # 策略3: 在指定品牌内，尝试多种前缀剥离方式
            stripped_names = self._strip_brand_prefixes(ename, db_brand)
            # 同时也剥离标准化名称的前缀
            stripped_normalized = self._strip_brand_prefixes(normalized_ename, db_brand)
            for stripped in stripped_names + stripped_normalized:
                # 去除括号内容（如 (25支)）
                cleaned = re.sub(r'\s*[（(].*?[）)]\s*', '', stripped).strip()
                # 标准化 cleaned
                cleaned_norm = self._normalize_name(cleaned)
                for name in [stripped, cleaned, cleaned_norm]:
                    if not name:
                        continue
                    cigars = Cigar.objects.filter(brand=db_brand, english_name__iexact=name)
                    if cigars.exists():
                        return cigars.first()
                    # 对 DB 侧也做 accent-insensitive 匹配
                    for c in Cigar.objects.filter(brand=db_brand):
                        if self._normalize_name(c.english_name).upper() == name.upper():
                            return c

            # 策略4: 在指定品牌内，english_name 包含匹配（子串）
            for stripped in stripped_names + stripped_normalized:
                cleaned = re.sub(r'\s*[（(].*?[）)]\s*', '', stripped).strip()
                cleaned_norm = self._normalize_name(cleaned)
                for name in [stripped, cleaned, cleaned_norm]:
                    if not name or len(name) < 3:
                        continue
                    cigars = Cigar.objects.filter(brand=db_brand, english_name__icontains=name)
                    if cigars.exists():
                        return cigars.first()
                    # accent-insensitive 子串匹配
                    for c in Cigar.objects.filter(brand=db_brand):
                        if name.upper() in self._normalize_name(c.english_name).upper():
                            return c

            # 策略5: 在指定品牌内，用 english_name 的前几个词匹配
            words = cleaned_norm.split() if cleaned_norm else normalized_ename.split()
            if len(words) >= 2:
                pattern = ' '.join(words[:2]).upper()
                for c in Cigar.objects.filter(brand=db_brand):
                    if pattern in self._normalize_name(c.english_name).upper():
                        return c

        # 策略6: 全局子串匹配（fallback）
        cigars = Cigar.objects.filter(english_name__icontains=normalized_ename)
        if cigars.exists():
            return cigars.first()

        return None

    def _strip_brand_prefixes(self, name: str, brand: str) -> list:
        """生成多种可能的品牌前缀剥离结果"""
        results = [name]
        upper_name = name.upper()

        # 生成各种可能的品牌前缀形式
        prefixes = set()
        prefixes.add(brand.upper())
        prefixes.add(brand.upper().replace(' ', ''))
        prefixes.add(brand.upper().replace('. ', ''))
        prefixes.add(brand.upper().replace('.', ''))
        prefixes.add(brand.upper().replace("'", ''))
        prefixes.add(brand.upper().replace("'", ' '))

        # 特殊处理
        if brand == 'Partagás':
            prefixes.add('PARTAGAS')
        if brand == 'Ramón Allones':
            prefixes.add('RAMON ALLONES')
        if brand == 'José L. Piedra':
            prefixes.add('JOSE L.PIEDRA')
            prefixes.add('JOSE L PIEDRA')
        if brand == 'H. Upmann':
            prefixes.add('H.UPMANN')
            prefixes.add('H. UPMANN')
        if brand == "Quai d'Orsay":
            prefixes.add("QUAI D'ORSAY")
            prefixes.add("QUAI D ORSAY")

        for prefix in prefixes:
            if upper_name.startswith(prefix + ' '):
                stripped = name[len(prefix):].strip()
                if stripped and stripped not in results:
                    results.append(stripped)

        return results

    def _parse_design_file(self):
        """解析 .opendesign/privnote-create.html 中的 quoteProducts 数组"""
        design_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            '.opendesign', 'privnote-create.html'
        )
        if not os.path.exists(design_path):
            self.stdout.write(self.style.ERROR(f'设计稿文件不存在: {design_path}'))
            return []

        with open(design_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 提取 quoteProducts 数组内容
        m = re.search(r'const\s+quoteProducts\s*=\s*(\[.*?\]);\s*$', content, re.DOTALL | re.MULTILINE)
        if not m:
            self.stdout.write(self.style.ERROR('无法在设计稿中找到 quoteProducts 数组'))
            return []

        array_text = m.group(1)

        # 提取所有 brand 分组
        results = []
        brand_pattern = re.compile(
            r"\{\s*brand:\s*['\"](.+?)['\"]\s*,\s*items:\s*\[(.*?)\]\s*\}",
            re.DOTALL
        )
        item_pattern = re.compile(
            r"\{\s*id:\s*['\"].*?['\"]\s*,\s*name:\s*['\"](.+?)['\"]\s*,\s*cn:\s*['\"](.+?)['\"]\s*,\s*qty:\s*(\d+)\s*,\s*price:\s*(\d+)\s*(?:,\s*inStock:\s*(?:true|false))?\s*\}"
        )

        for brand_match in brand_pattern.finditer(array_text):
            brand_name = brand_match.group(1)
            items_text = brand_match.group(2)
            for item_match in item_pattern.finditer(items_text):
                name = item_match.group(1)
                cn = item_match.group(2)
                qty = int(item_match.group(3))
                price = int(item_match.group(4))
                results.append({
                    'english_name': name,
                    'box_size': qty,
                    'wholesale_price': price,
                    'cn_name': cn,
                    'brand': brand_name,
                    'sort_order': 0,
                    'is_active': True,
                })

        self.stdout.write(self.style.SUCCESS(f'从设计稿解析出 {len(results)} 款雪茄数据'))
        return results

    def _get_sample_data(self):
        """示例数据 — 用于测试结构，生产环境请提供实际数据文件"""
        return [
            # {"english_name": "COHIBA ROBUSTOS", "box_size": 25, "wholesale_price": 17900, "sort_order": 1},
        ]
