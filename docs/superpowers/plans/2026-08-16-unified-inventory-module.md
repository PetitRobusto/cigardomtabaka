# 统一库存 Module 第一阶段 Implementation Plan

> **For agentic workers:** 按项目风险门禁执行；本计划不要求强制 TDD，不使用 Kanban。

**Goal:** 将现有七类库存动作收口到一个受控 Module，并从模型层阻止普通 ORM 绕过库存事实。

**Architecture:** 新建库存写入作用域与库存 Module。现有 Day 1、采购、销售和会计命令保留自己的业务状态及账务职责，只委托库存 Module 更新批次、分配和流水。

**Tech Stack:** Django 5、Python、SQLite/PostgreSQL 兼容事务、Django TestCase

---

### Task 1：建立库存写入作用域和模型门禁

**Files:**
- Create: `cigars/inventory_scope.py`
- Modify: `cigars/models.py`
- Modify: `cigars/admin.py`
- Test: `cigars/tests/test_inventory_write_boundary.py`

- [x] 定义按动作原因、模型和字段白名单校验的库存写入作用域。
- [x] 为 `PurchaseBatch`、`StockAllocation`、`StockMovement` 增加实例与 QuerySet 写保护。
- [x] 保证流水不可改删、分配关键字段不可变、批次库存字段只能受控写入。
- [x] 将三个库存事实的 Django Admin 设为只读。
- [x] 覆盖普通 `save/update/delete/bulk_*` 被拒绝及合法作用域可写入。

### Task 2：建立统一库存 Module

**Files:**
- Create: `cigars/inventory.py`
- Create: `cigars/audit.py`
- Test: `cigars/tests/test_inventory_module.py`

- [x] 将 Agent 审计上下文移到无循环依赖的 `cigars.audit`。
- [x] 实现期初、采购入库、FIFO 预留、整单释放、整单出库、调整和拆盒动作。
- [x] 每个动作在单一库存作用域中同步维护批次、分配和流水。
- [x] 为数量非负、包装形态、分配状态和成本守恒补关键行为测试。

### Task 3：迁移现有调用方

**Files:**
- Modify: `accounting/day1.py`
- Modify: `accounting/purchase_actions.py`
- Modify: `cigars/services.py`
- Modify: `cigars/sales_accounting.py`
- Modify: affected test fixtures under `accounting/tests/`, `cigars/tests/`, `privnote/tests.py`

- [x] Day 1 通过 `open_stock` 建立期初库存。
- [x] 采购到货通过 `receive_stock` 建立批次。
- [x] 销售确认、取消和出库分别通过 reserve、release、ship 动作。
- [x] 调整和拆盒命令委托库存 Module；会计分录仍由原命令同事务完成。
- [x] 删除四个调用方中已被 Module 接管的直接库存写入实现。
- [x] 测试夹具通过明确的测试库存作用域建立历史或异常事实，不给业务代码留通用写入口。

### Task 4：目标验证与独立审查

**Files:**
- Modify: review fixes within current scope only

- [x] 运行库存 Module、Day 1、采购、销售工作流、销售会计和 Agent 库存目标测试。
- [x] 运行 Django system check、迁移一致性检查和相关测试集合。
- [x] 进行一次实现期独立审查并修复 Critical/Important。
- [x] 重新运行受影响验证，进行最终独立审查。
- [ ] 提交中文 commit，合并回 `main`，删除功能分支；不 push。
