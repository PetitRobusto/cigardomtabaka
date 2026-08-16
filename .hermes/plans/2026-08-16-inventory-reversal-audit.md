# 库存反向动作、审计与帮助引导计划

## 目标

保留原业务事实，通过追加反向库存流水和账务冲正，支持采购到货撤销、整单销售退货、库存调整撤销，并提供只读库存审计和可操作的中文帮助引导。

## 范围

- 后端：模型、迁移、库存服务、账务冲正、Web/Agent API、报表。
- 前端：三类反向动作入口、审计入口、状态展示和错误提示。
- Help：真实场景说明；主要业务流程按字段和动作逐步高亮，不自动提交写操作。

## 执行清单

- [x] 建立反向动作模型、迁移和账务冲正边界。
- [x] 实现采购到货撤销、销售整单退货和库存调整撤销。
- [x] 实现库存一致性审计及 Web/Agent API。
- [x] 接入前端操作入口和最近调整列表。
- [x] 完成第一轮独立审查并修复 Critical/Important。
- [x] 扩充所有主要 Help 互动引导并核对真实定位点。
- [x] 运行相关后端回归、前端测试、类型检查、Lint 和构建。
- [x] 完成第二轮独立审查并修复 Critical/Important。
- [x] 中文提交、本地合并 `main`、合并后复验并删除功能分支。

## 验证

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test accounting.tests cigars.tests.test_inventory_audit cigars.tests.test_inventory_adjustment_reversal cigars.tests.test_inventory_write_boundary cigars.tests.test_sales_fulfillment cigars.tests.test_sales_order_api cigars.tests.test_sales_refund_transport
cd frontend && npm run typecheck && npm run lint && npm run test -- --run && npm run build
git diff --check
```

默认不 push，不修改生产数据。

最终验证：后端 571 项、前端 167 项全部通过；TypeScript、ESLint、生产构建、Django check、迁移检查和 diff 检查通过。
