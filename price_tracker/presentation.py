"""Read-only snapshot metadata shared by price APIs; never infer anomaly flags."""


def product_name(snapshot):
    raw = snapshot.raw_data if isinstance(snapshot.raw_data, dict) else {}
    for key in ('title_original', 'product_name', 'title', 'product'):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


def anomaly_info(snapshot):
    if not snapshot.is_anomalous:
        return None
    return {
        'code': 'outlier',
        'label': '价格异常',
        'reason': '后端已标记同款同盒规 IQR 离群；未保存检测时的阈值与偏离幅度，需人工核验。',
        'exclude_from_aggregate': True,
    }
