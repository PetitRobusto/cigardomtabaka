# 首页光影特效发布 — 2026-10-29

用户确认取消远景雪茄下落实验，并授权将此前确认的前景效果合并、部署。

范围：首页五支雪茄保持现有响应式 WebP、三语内容与商品/品牌链接；采用已确认的纯色暖调舞台、金色光泽和柔和地面投影。Hover/键盘聚焦以当前姿态为中心轻摆，垂直幅度为自由漂浮的 22%，绕雪茄中点旋转 ±0.35°。离开时继续原自由相位和周期，微小姿态偏移在一个正常周期内消退，无追赶。增加三语暂停按钮；页面隐藏、离屏和系统减少动态效果时暂停；卸载时取消动画并清理监听与观察器。

实现使用 WAAPI transform/opacity，事件和 resize 时生成关键帧，不逐帧执行 JavaScript。SSR 保留静态五支雪茄与链接；不支持所需浏览器 API 时保持静态。没有引入背景图片、远景下落、媒体上传、数据库或配置修改。未纳入原工作区的品牌图与 SEO 未提交改动。

## 本地验证

- TypeScript、ESLint、生产客户端/SSR build 通过。
- 前端 104 文件、650 测试通过。机器为 Node 25，使用 `NODE_OPTIONS=--no-experimental-webstorage` 关闭其与 jsdom 冲突的实验接口；CI 使用仓库既有 Node 20。
- Django `storefront.tests.test_render_integration` 7 测试通过，DEBUG=True、独立测试库。
- 浏览器中文/英文/俄文，1440px 与 390px：图片加载、SSR hydration、无横向溢出、无 JS 错误。
- 实际 WAAPI 共 120 组进入/离开 hover 验证：姿态连续、原播放速率 1、持续时间不缩短；真实指针、暂停、减少动态效果、离屏暂停与 SPA 卸载清理通过。
- Luna 独立审查无 Critical/Important；按审查去除 stage paint containment，避免裁切键盘焦点框。
- 截图及原始验收结果保存在本地 `/tmp/hero-local/`，不提交构建或媒体。

## 发布门禁

以 `origin/main` 的 `f00e484` 为基线；此前线上准确 SHA 为 `a2ec9468fc8c2d813a97761181b210342f0c23e7`，CI 和 Deploy 均成功。

使用现有 `push main → CI → Deploy` 流程；只部署通过 CI 的准确 SHA 与对应前端 artifact。上线后核对 CI/Deploy、公开 HTTP 门禁、三语实际浏览器表现。若需回退，用新的回退提交重新通过完整 CI，不绕过部署门禁。
