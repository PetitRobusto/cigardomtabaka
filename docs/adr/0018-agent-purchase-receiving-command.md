# 0018 — Agent 采购入库采用草稿确认后整单入库

**状态：** 已采纳  
**日期：** 2026-06-15  
**决策者：** 板儿面

Agent 的正式采购入库不使用库存修正冒充，也不开放通用 CRUD；采购流程拆成 `create_purchase_order` 和 `receive_purchase_order` 两个命令。第一步只创建不可修改的采购单草稿和明细，第二步由 agent 二次确认后整单一次性入库，创建 Purchase Batch 并写 `receive` 类型 Stock Movement。

第一版不支持草稿修改、部分入库、自动创建 Supplier 或 PurchaseEvent。Supplier 必须预先登记并通过 ID 引用；采购金额以行级 RUB 单价和整单汇率为输入口径，CNY 单价与总额由系统计算。这样牺牲了部分灵活性，但保持了小团队可维护的业务复杂度，并让正式入库、库存流水和幂等审计边界保持清晰。
