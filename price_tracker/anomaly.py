"""价格异常检测 — IQR（四分位距）方法"""

import logging
from collections import defaultdict
from django.db.models import Q

logger = logging.getLogger(__name__)


def detect_and_mark_group(cigar_id: int, box_size: int) -> int:
    """
    对指定 (cigar_id, box_size) 组内所有 snapshot 做 IQR 异常检测。
    返回标记为异常的条数。
    """
    from price_tracker.models import PriceSnapshot

    snaps = list(
        PriceSnapshot.objects.filter(
            cigar_id=cigar_id,
            box_size=box_size,
            price_cny__isnull=False,
        ).order_by('price_cny')
    )

    n = len(snaps)
    if n < 4:
        # 样本太少，不够统计意义——全部清异常标记
        updated = PriceSnapshot.objects.filter(
            cigar_id=cigar_id, box_size=box_size, is_anomalous=True
        ).update(is_anomalous=False)
        if updated:
            logger.info(f'[anomaly] cigar={cigar_id} box={box_size}: '
                        f'n={n} < 4, 清除 {updated} 条异常标记')
        return 0

    # 计算 Q1, Q3, IQR
    prices = [s.price_cny for s in snaps]

    def percentile(data, p):
        """线性插值分位数"""
        k = (len(data) - 1) * p
        f = int(k)
        c = k - f
        if f + 1 < len(data):
            return data[f] + c * (data[f + 1] - data[f])
        return data[f]

    q1 = percentile(prices, 0.25)
    q3 = percentile(prices, 0.75)
    iqr = q3 - q1
    lower = q1 - 3 * iqr
    upper = q3 + 3 * iqr

    anomalous = 0
    for snap in snaps:
        is_anom = snap.price_cny < lower or snap.price_cny > upper
        if snap.is_anomalous != is_anom:
            snap.is_anomalous = is_anom
            snap.save(update_fields=['is_anomalous'])
            if is_anom:
                anomalous += 1
                logger.info(f'[anomaly] cigar={cigar_id} box={box_size} '
                            f'snap={snap.id} price_cny={snap.price_cny:.0f} '
                            f'范围=[{lower:.0f}, {upper:.0f}] → 异常')

    logger.info(f'[anomaly] cigar={cigar_id} box={box_size}: '
                f'n={n} Q1={q1:.0f} Q3={q3:.0f} IQR={iqr:.0f} '
                f'异常={anomalous}/{n}')
    return anomalous


def recalc_all():
    """全量重算所有分组的异常标记"""
    from price_tracker.models import PriceSnapshot

    # 找所有有足够数据的 (cigar_id, box_size) 组合
    groups = (
        PriceSnapshot.objects
        .filter(price_cny__isnull=False)
        .values('cigar_id', 'box_size')
        .distinct()
    )

    total_anomalous = 0
    for g in groups:
        cid = g['cigar_id']
        bs = g['box_size']
        total_anomalous += detect_and_mark_group(cid, bs)

    return total_anomalous


def recalc_for_snapshot(snapshot):
    """单个 snapshot 变更后，重算其所在组"""
    return detect_and_mark_group(snapshot.cigar_id, snapshot.box_size)
