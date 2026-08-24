# 0004 — RapidFuzz 替代 fuzzywuzzy 做雪茄名匹配

**状态：** 已采纳  
**日期：** 2026-05  
**决策者：** 板儿面

---

## 背景

爬虫从外部网站抓取的雪茄名称需要匹配到本地数据库的 Cigar 记录。名字格式千差万别（"Cohiba Siglo VI" vs "Siglo VI Cohiba SLB 25"），需要模糊匹配引擎。

旧方案用 `fuzzywuzzy`，但存在性能瓶颈和匹配精度问题（尤其是多词重排场景）。

## 选项

| 方案 | 描述 | 速度 | 匹配能力 |
|------|------|------|----------|
| A: fuzzywuzzy | Python 原生实现 | 慢 | 基础 ratio / partial_ratio |
| B: RapidFuzz | C++ 后端，API 兼容 | 快 10-50x | token_set_ratio / token_sort_ratio / WRatio |
| C: difflib | Python 标准库 | 中 | 仅 SequenceMatcher |

## 决策

**选 B：RapidFuzz。** 关键改变：用 `token_set_ratio` 替代 `WRatio`。

- `token_set_ratio`：把两个字符串拆成词袋，求交集/并集比率。天然适应词序不同的问题
- 阈值 80 + 15 种品牌状态 + 5 个品牌提示词（hint）
- 缓存匹配结果避免重复计算

## 后果

**好处：**
- 匹配速度提升 10-50 倍（C++ 后端）
- token_set_ratio 对跨品牌误匹配有天然抗性（词袋不关心顺序）
- MIT 许可证，无依赖顾虑

**代价：**
- 多了一个 C++ 编译依赖（`pip install rapidfuzz` 需要编译器）
- token_set_ratio 对短名称（1-2 词）不如 WRatio

## 参考

- `price_tracker/matcher.py` — 匹配引擎全部逻辑
- `cigar-query` skill → 匹配器说明
