"""下架检测 —— 对比爬取结果 vs 历史，标记下架事件"""
import logging
from django.db.models import Max
from django.utils import timezone
from .models import PriceSnapshot

logger = logging.getLogger(__name__)


def detect_delistings(source, scraped_combos):
    """检测已下架的雪茄组合。

    Args:
        source: PriceSource 实例
        scraped_combos: set of (cigar_id, box_size) 今天爬到的组合

    Returns:
        {'newly_delisted': int, 'already_delisted': int}
    """
    today = timezone.localdate()

    # 1. 找到上一次爬取中仍在售的 combo（不是全部历史！）
    #    只对比 "上次有 → 这次无" 的才标记下架，避免历史累积导致每天重复标记
    last_scrape_date = (
        PriceSnapshot.objects
        .filter(source=source, in_stock=True)
        .exclude(scraped_date=today)
        .aggregate(last=Max('scraped_date'))['last']
    )

    if not last_scrape_date:
        logger.debug('Source %s has no pre-today in-stock snapshots, skipping.', source.slug)
        return {'newly_delisted': 0, 'already_delisted': 0}

    prev_combos = (
        PriceSnapshot.objects
        .filter(source=source, scraped_date=last_scrape_date, in_stock=True)
        .values_list('cigar_id', 'box_size')
        .distinct()
    )

    if not prev_combos:
        logger.debug('Source %s: no in-stock combos on %s, skipping.', source.slug, last_scrape_date)
        return {'newly_delisted': 0, 'already_delisted': 0}

    logger.debug(f'[delisting] comparing {len(prev_combos)} prev combos (from {last_scrape_date}) '
                 f'vs {len(scraped_combos)} today')

    newly_delisted = 0
    already_delisted = 0

    for cigar_id, box_size in prev_combos:
        combo = (cigar_id, box_size)

        # 2. 如果今天还在 → 跳过
        if combo in scraped_combos:
            continue

        # 3. 检查今天是否已有 in_stock=False 的快照
        already_oos_today = PriceSnapshot.objects.filter(
            source=source,
            cigar_id=cigar_id,
            box_size=box_size,
            scraped_date=today,
            in_stock=False,
        ).exists()

        if already_oos_today:
            already_delisted += 1
            logger.debug(
                'Combo %s already marked OOS today for source %s.',
                combo, source.slug,
            )
            continue

        # 4. 获取最新的 in_stock=True 快照作为参考
        last_active = (
            PriceSnapshot.objects
            .filter(source=source, cigar_id=cigar_id, box_size=box_size, in_stock=True)
            .order_by('-scraped_at')
            .first()
        )
        if not last_active:
            continue

        # 5. 创建下架快照
        PriceSnapshot.objects.create(
            source=source,
            cigar_id=cigar_id,
            price=last_active.price,
            currency=last_active.currency,
            price_cny=last_active.price_cny,
            box_size=box_size,
            box_price=last_active.box_price,
            in_stock=False,
            url=last_active.url,
            scraped_date=today,
            scraped_at=timezone.now(),
            raw_data={
                'delisted': True,
                'delisted_at': timezone.now().isoformat(),
                'last_seen': str(last_active.scraped_date),
            },
        )
        newly_delisted += 1
        logger.info('Marked %s as delisted for source %s.', combo, source.slug)

    logger.info(
        'Delisting scan for %s: %d newly delisted, %d already delisted.',
        source.slug, newly_delisted, already_delisted,
    )
    return {
        'newly_delisted': newly_delisted,
        'already_delisted': already_delisted,
    }
