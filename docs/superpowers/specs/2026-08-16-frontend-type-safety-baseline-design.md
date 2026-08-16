# 前端类型安全基线设计

## 背景

`/help/` 曾因 `ChapterButton` 定义被误删而在浏览器运行时报错。现有流水线仍然通过，原因是 Vite 只转译 TypeScript、不执行类型检查，ESLint 只匹配 JavaScript，CI 也没有运行 Vitest。手动执行完整类型检查后，当前基线为 50 个错误、17 个文件。

## 目标

- 保持 TypeScript `strict`，清零源码和测试中的全部类型错误。
- 让 `npm run build` 在类型错误存在时失败。
- 让 ESLint 实际检查 `.ts` 和 `.tsx`，并禁止“文件被忽略但命令成功”。
- 让 CI 运行类型检查、Lint、Vitest 和生产构建；任一失败都阻止 production 部署。
- 通过真实类型、空值分支和运行时边界检查修复问题，不使用 `any`、批量断言或关闭规则掩盖错误。

## 非目标

- 不改页面布局、视觉设计或业务流程。
- 不处理 Vite 的 bundle-size 警告。
- 不重构 Django API；只有在确认前端类型与真实响应不一致时才校正契约类型。

## 方案

### TypeScript 基线

保留一个覆盖 `src`（包括测试）的严格 `tsconfig.json`。移除 TypeScript 6 已弃用的 `baseUrl` 配置，同时保留相对 `paths` 映射。新增 `typecheck` 脚本执行 `tsc --noEmit`，并让 `build` 在 Vite 打包前执行该脚本。

错误按依赖顺序修复：

1. 共享 API 响应泛型和领域类型。
2. 会计动作组件及其测试夹具。
3. 价格目录、图表、导航和价格数据工具。
4. Privnote、提醒页面及其测试夹具。

共享类型只根据后端接口和实际消费方式调整。可空金额、包装数量和图表回调值必须显式收窄，不能用非空断言绕过。

### ESLint 基线

引入 TypeScript ESLint 的 flat-config 支持，让现有 React Hooks 和 React Refresh 规则同时覆盖 `.ts/.tsx`。Lint 命令使用零警告门禁；若配置再次漏掉 TypeScript 文件，CI 会失败而不是静默通过。

### CI 与部署

前端 CI 顺序为安装锁定依赖、Lint、Vitest、build。build 内含 typecheck，因此任何未定义标识符或接口漂移都会在产出静态文件前失败。现有 Deploy workflow 只在 `CI` 成功后运行，因此失败不会更新 production。

## 验证

- RED 基线：`tsc --noEmit --ignoreDeprecations 6.0` 报告 50 个错误。
- 每组修复后运行对应 Vitest 文件，防止类型修复改变行为。
- 最终必须满足：`npm run typecheck`、`npm run lint`、`npm test -- --run`、`npm run build` 全部退出 0。
- 检查 GitHub Actions YAML 和 `git diff --check`。
- 生产部署只在用户明确 push 后由成功的 CI 触发；本任务不自动 push。

## 风险控制

- 类型定义与后端响应不一致时，先核对 serializer/view，再修改前端类型。
- Recharts 等第三方回调通过官方联合类型和空值保护适配，不使用 `any`。
- 测试夹具补齐真实必填字段，避免 `as never` 继续掩盖契约漂移。
- 分批提交并至少进行两轮审查：类型契约审查和最终 CI/回归审查。
