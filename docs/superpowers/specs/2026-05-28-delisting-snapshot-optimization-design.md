# 下架检测 + 快照去重 设计文档

> 日期：2026-05-28 | 状态：approved

## 目标

1. **快照去重**：价格不变不记录，减少数据膨胀
2. **下架检测**：独立模块，首次发现商品消失时记录下架事件
3. **前端展示**：下架商品灰显 + 标签

## 架构

```
爬取(scrape) → 匹配(match) → [快照去重] → 只记价格变化
                                    ↓
                              [下架检测] → 对比本次 vs 历史，标记下架/重新上架
```

两个独立模块，职责清晰，互不耦合。

## 模块1：快照去重

### 改造位置
`price_tracker/scraper.py` — `run_scrape_sync()` 函数

### 逻辑

对每个爬取到的 (cigar, source, box_size)：

```python
latest = PriceSnapshot.objects.filter(
    source=source, cigar=cigar, box_size=box_size
).order_by('-scraped_at').first()

if latest is None:
    # 新商品 → 创建
    INSERT
elif latest.in_stock == False:
    # 之前下架/缺货，现在回来了 → 创建 relisted 快照
    INSERT with raw_data={'relisted': True, ...}
elif latest.price != item.price:
    # 价格变了 → 创建
    INSERT
else:
    # 价格没变 → 跳过
    pass
```

### 需要移除
- `uq_snapshot_per_day` 唯一约束（migration）
- `scraped_date` 字段上的 `auto_now_add` 不变，但不再依赖每日去重

## 模块2：下架检测

### 位置
新建 `price_tracker/delisting.py`

### 接口

```python
def detect_delistings(source: PriceSource, scraped_combos: set[tuple[int, int]]) -> dict:
    """
    对比本次爬取结果 vs 历史活跃商品，标记下架。

    Args:
        source: 价格来源
        scraped_combos: 本次爬取到的 {(cigar_id, box_size), ...}

    Returns:
        {'newly_delisted': int, 'already_delisted': int}
    """
```

### 逻辑

1. 查该 source 所有"最新快照 in_stock=True"的组合
2. 不在 `scraped_combos` 中的 → 判定首次下架
3. 检查今天是否已有 in_stock=False 的快照 → 有则跳过（避免重复）
4. 创建 in_stock=False 快照，raw_data 标记：
   ```json
   {"delisted": true, "delisted_at": "2026-05-28T...", "last_seen": "2026-05-27"}
   ```

### 集成方式
在 `run_scrape_sync()` 末尾调用，替换现有 scraper.py 169-216 行的内联缺货检测。

## 模块3：重新上架检测

内置在下架检测模块中——当某 combo 之前最新快照 in_stock=False，但本次爬取到了 → 创建 in_stock=True 快照，raw_data 标记 `{"relisted": true}`。

这部分在快照去重模块中处理（见到 `latest.in_stock == False` 就 INSERT）。

## 数据模型

**不新建表，不新增字段。** 只通过 `raw_data` 标记：

| 事件 | raw_data 标记 |
|------|-------------|
| 下架 | `{"delisted": true, "delisted_at": "ISO datetime"}` |
| 重新上架 | `{"relisted": true, "relisted_at": "ISO datetime"}` |
| 缺货（兼容旧数据） | `{"oos_detected": true, "last_seen": "date"}` |

### 为什么不用新表
- 下架本身就是一个 in_stock=False 的 PriceSnapshot，新表只是冗余
- raw_data (JSONField) 灵活且已有查询能力
- 保持简单，不增加 migration 复杂度

## 前端改动

### PriceCard / PriceRow（Dashboard）
- in_stock=False 时灰显，价格划掉
- 显示「缺货」标签（已有）

### VariantCard（详情页）
- 已有「现货/缺货」标签，无需改

### 新增：下架专属标签
- 读取 raw_data.delisted → 显示「已下架」（红色）vs「缺货」（黄色）

## 影响范围

| 文件 | 操作 |
|------|------|
| `price_tracker/scraper.py` | **重构** run_scrape_sync：快照去重 + 调用 delisting 模块 |
| `price_tracker/delisting.py` | **新建** 下架检测模块 |
| `price_tracker/models.py` | **微调** 移除 uq_snapshot_per_day 约束 |
| `price_tracker/views.py` | 无需改（raw_data 已在序列化器输出） |
| `price_tracker/serializers.py` | 无需改 |
| `frontend/src/components/dashboard/PriceCard.tsx` | 下架状态灰显 |
| `frontend/src/components/detail/VariantCard.tsx` | 区分「缺货」vs「已下架」标签 |

## 不变的部分

- PriceSnapshot 模型结构不变
- API 接口不变
- 爬虫（scrapers/）不变
- 前端路由/布局不变
