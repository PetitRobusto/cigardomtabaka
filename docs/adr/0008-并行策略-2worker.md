# 0008 — Scrape 并行 2 Worker + Push 串行

**状态：** 已采纳  
**日期：** 2026-06-06  
**决策者：** 板儿面

---

## 背景

爬取阶段有 7 个活跃源，push 阶段逐一推送到生产。需要决定并行策略。

## 选项

| 阶段 | 方案 | 描述 |
|------|------|------|
| 爬取 | A: 全串行 | 一个接一个爬 |
| 爬取 | B: 全并行 (asyncio) | 所有源同时爬 |
| 爬取 | C: ThreadPool 2 worker | 最多 2 个同时 |
| 推送 | A: 并行 POST | 同时推所有源 |
| 推送 | B: 串行 POST | 一个一个推 |

## 决策

**爬取：ThreadPoolExecutor(max_workers=2)**

- 不是 asyncio：Django ORM 在 async 上下文里需要 `sync_to_async` 包装，增加复杂度
- 不是全并行 7：机器只有 2 核，7 个 Playwright 同时跑内存直接炸（见 ADR-0002）
- 2 worker 刚好：Nyon（~180s）和其他源并行，总时长 ~210s

**推送：串行**

- 生产服务器是单实例 SQLite，并发 POST 会导致 DB 锁竞争
- push 本身很快（30s 内），串行不构成瓶颈
- 简单可靠，失败不影响其他源

## 后果

**好处：**
- 爬取在内存和速度间取得平衡（2 worker 是甜点）
- 推送不会引发生产端 DB 锁
- 实现简单（ThreadPool + for loop），无需 asyncio 胶水代码

**代价：**
- 如果有大量新源加入，2 worker 会成为瓶颈（但当前 7 个源已够用）
- 推送串行意味着一个源慢就拖慢整体（但单个源很少超过 15s）

## 参考

- `tools/scrape.py:79` — `ThreadPoolExecutor(max_workers=2)`
- `tools/push_prices.py:100` — 串行 for 循环
