# 0001 — Nyon 独立 headless Chromium + stealth

**状态：** 已采纳  
**日期：** 2026-06-10  
**决策者：** 板儿面

---

## 背景

LCDH Nyon 有 Cloudflare 防护。其他 3 个 Playwright 爬虫统一使用 CDP 浏览器（Chrome 常驻 9222 端口），通过 `connect_over_cdp()` 复用。

Nyon 从第一版代码就选择了独立 Chromium（`chromium.launch(headless=True)`），不连 CDP。配合 `playwright_stealth` 插件修改浏览器指纹和 User-Agent，伪装成普通 Windows Chrome。

## 当前方式

```python
# lcdh_nyon.py — 独立启动，不连 CDP
browser = await p.chromium.launch(
    headless=True,
    args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
)
# stealth 修改指纹
stealth = Stealth()
await stealth.apply_stealth_async(page)
```

- 单 browser 跑全部 28 品牌
- page 被销毁或连续 3 品牌失败 → 重建 page（不重启 browser）
- 使用 `page.evaluate(fetch())` 抓取各品牌分类页的 HTML
- 全量 ~336 款，耗时约 210s

## 为什么独立而不是 CDP

1. **实际代码就是独立启动**，从一开始就没用过 CDP（git log 可查）
2. Playwright 升级后 browser 版本可能变化，独立启动确保使用 Playwright 管理的版本
3. stealth 插件在每个新 browser 上效果一致，不依赖 CDP 的已有状态

## 后果

**好处：**
- 不依赖 CDP Chrome 常驻进程
- stealth 每次生效，不受 CDP 已有指纹影响
- page 级恢复快，不触发 EPIPE

**代价：**
- 每次需独立启动 Chromium（+3-5s）
- 需保留 Playwright 安装的浏览器版本（当前 `chromium_headless_shell-1208`）
- 内存占用比 CDP 多 ~500MB（独立 browser 进程）

## 测试验证 (2026-06-12)

```
[lcdh_nyon] ✅: 336 items, 322 matched (96%), 46 new snapshots, 0 OOS
```

## 参考

- `price_tracker/scrapers/lcdh_nyon.py:68` — `chromium.launch(headless=True)`
- `playwright_stealth` — 指纹伪装库
