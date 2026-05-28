"""下架检测模块测试"""
import pytest
from django.utils import timezone
from datetime import timedelta

from price_tracker.models import PriceSource, PriceSnapshot
from price_tracker.delisting import detect_delistings
from cigars.models import Cigar, Brand


@pytest.mark.django_db
class TestDetectDelistings:
    """detect_delistings() 函数测试"""

    @staticmethod
    def _make_source(name='Test Source', slug='test-source', scraper_class='test'):
        return PriceSource.objects.create(
            name=name, slug=slug,
            base_url='https://example.com',
            scraper_class=scraper_class,
        )

    @staticmethod
    def _make_brand(name='Test Brand', english_name='Test Brand'):
        return Brand.objects.create(name=name, english_name=english_name)

    @staticmethod
    def _make_cigar(brand='Test Brand', english_name='Test Cigar'):
        return Cigar.objects.create(brand=brand, english_name=english_name)

    @staticmethod
    def _make_snapshot(source, cigar, box_size=25, in_stock=True, days_ago=1, **kwargs):
        """创建历史快照。days_ago 控制 scraped_date"""
        now = timezone.now()
        scraped_at = now - timedelta(days=days_ago)
        # 因为 scraped_date 是 auto_now_add，需要用 _meta 绕过
        snap = PriceSnapshot(
            source=source,
            cigar=cigar,
            price=100.0,
            box_size=box_size,
            in_stock=in_stock,
            scraped_at=scraped_at,
            scraped_date=scraped_at.date(),
            **kwargs,
        )
        # 使用 update_or_create 方式手动设 scraped_date
        snap.save()
        # 直接 update 设置 scraped_date（auto_now_add 只在 insert 时生效）
        PriceSnapshot.objects.filter(pk=snap.pk).update(
            scraped_date=scraped_at.date(),
            scraped_at=scraped_at,
        )
        return PriceSnapshot.objects.get(pk=snap.pk)

    # ── test 1: 新下架 → 创建 in_stock=False 快照 ──────────────────────────
    def test_new_delisting_creates_snapshot(self):
        """昨日有货、今日未出现在爬取结果 → 创建 in_stock=False 快照"""
        source = self._make_source(slug='test-delist-1')
        cigar = self._make_cigar(english_name='Delist Cigar 1')
        box_size = 25

        # 昨天有货
        self._make_snapshot(source, cigar, box_size=box_size, in_stock=True, days_ago=1)

        # 今日爬取结果：空（cigar 不在里面）
        scraped_combos = set()

        result = detect_delistings(source, scraped_combos)

        assert result['newly_delisted'] == 1
        assert result['already_delisted'] == 0

        # 验证创建了 in_stock=False 快照
        oos = PriceSnapshot.objects.filter(
            source=source, cigar=cigar, box_size=box_size,
            in_stock=False, scraped_date=timezone.now().date(),
        )
        assert oos.exists()
        snap = oos.first()
        assert snap.raw_data.get('delisted') is True
        assert 'delisted_at' in snap.raw_data
        assert 'last_seen' in snap.raw_data

    # ── test 2: 已下架跳过 ────────────────────────────────────────────────
    def test_already_delisted_skips(self):
        """最新快照已是 in_stock=False → 不重复创建"""
        source = self._make_source(slug='test-delist-2')
        cigar = self._make_cigar(english_name='Delist Cigar 2')
        box_size = 25

        # 昨天有货（历史记录）
        self._make_snapshot(source, cigar, box_size=box_size, in_stock=True, days_ago=1)

        # 今天已标记为下架（模拟之前已跑过 detect_delistings）
        today = timezone.now().date()
        snap = PriceSnapshot.objects.create(
            source=source, cigar=cigar, price=100.0,
            box_size=box_size, in_stock=False,
            raw_data={'delisted': True},
        )
        PriceSnapshot.objects.filter(pk=snap.pk).update(scraped_date=today)

        scraped_combos = set()
        result = detect_delistings(source, scraped_combos)

        assert result['newly_delisted'] == 0
        assert result['already_delisted'] == 1
        # 确认没有新增重复下架快照
        oos_count = PriceSnapshot.objects.filter(
            source=source, cigar=cigar, box_size=box_size,
            in_stock=False, scraped_date=today,
        ).count()
        assert oos_count == 1

    # ── test 3: 仍在售不触发 ──────────────────────────────────────────────
    def test_still_active_no_delisting(self):
        """combo 出现在今天爬取结果中 → 不下架"""
        source = self._make_source(slug='test-delist-3')
        cigar = self._make_cigar(english_name='Active Cigar')
        box_size = 25

        # 昨天有货
        self._make_snapshot(source, cigar, box_size=box_size, in_stock=True, days_ago=1)

        # 今天仍出现在爬取结果中
        scraped_combos = {(cigar.id, box_size)}

        result = detect_delistings(source, scraped_combos)

        assert result['newly_delisted'] == 0
        assert result['already_delisted'] == 0

        # 确认没有 in_stock=False 快照
        oos_count = PriceSnapshot.objects.filter(
            source=source, in_stock=False,
        ).count()
        assert oos_count == 0

    # ── test 4: 无历史数据不触发 ──────────────────────────────────────────
    def test_no_history_no_delisting(self):
        """source 没有任何历史快照 → 不下架"""
        source = self._make_source(slug='test-delist-4')

        scraped_combos = {(999, 25)}  # 随便一个不存在的 combo
        result = detect_delistings(source, scraped_combos)

        assert result['newly_delisted'] == 0
        assert result['already_delisted'] == 0

        # 确认没有创建任何新快照
        assert PriceSnapshot.objects.filter(source=source).count() == 0
