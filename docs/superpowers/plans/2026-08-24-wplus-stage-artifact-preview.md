# W+ SOP 阶段与累计产物页面预览实施计划

## 目标

让阶段报告和累计 SOP 像最终结果一样在工作台内读取并呈现 JSON、Markdown、HTML，同时修复当前只按 `artifact_id` 下载、无法区分版本且后端只查询最终产物的问题。所有读取继续校验 W+ Session ownership，历史版本保持只读。

## 范围

- 阶段报告默认预览最新版本，可切换查看历史只读版本。
- 阶段、累计、最终 SOP 共用一致的 JSON / Markdown / HTML 页面预览交互。
- 阶段产物以 `stage_id + revision + report_no + artifact_id` 定位；累计产物以 `preview_version + artifact_id` 定位。
- 预览和下载通过带认证头的 W+ Session API 读取，不直接依赖前端持久公开 static URL。
- 不修改环节反馈、确认、累计生成和最终化的业务状态转换。

## 已确认技术决策

- 使用现有工作台内的 sandbox HTML 预览模式；JSON 和 Markdown 使用可滚动文本视图，JSON 在客户端格式化但不改变原始下载内容。
- 后端从持久化 Session 投影中解析目标产物，再从所属 Workspace static 目录返回文件；未知版本、未知产物、文件缺失或哈希不一致均 fail closed。
- 下载与预览共享同一读取端点，前端根据用途读取 text 或 blob。
- 历史版本被选中时只展示和下载，不改变“只能确认最新版本”的现有门控。

## 实施单元

### U1：先锁定版本化产物读取契约

**文件**

- `tests/unit/app/wplus_sop/test_router.py`
- `console/src/api/modules/wplusSop.test.ts`

**工作**

- 先新增失败测试，覆盖最终、阶段指定版本、累计指定版本的认证读取。
- 覆盖另一用户读取拒绝、未知 report/preview 404、文件缺失和哈希不一致。
- 前端 API 测试必须断言完整版本身份被编码进请求，不能只传 `artifact_id`。

**验证**

- RED：新增测试在现有只支持最终产物的路由/API 下失败。
- GREEN：U2 完成后上述测试通过。

### U2：实现 ownership-gated 产物读取

**文件**

- `src/swe/app/wplus_sop/router.py`
- `console/src/api/modules/wplusSop.ts`

**工作**

- 将最终产物读取改为直接返回经过校验的 Workspace 文件，而不是跳转到 static URL。
- 新增阶段指定版本与累计指定版本的读取路由。
- 校验 resolved path containment、文件存在和持久化 SHA-256。
- 为前端提供 text/blob 两种读取方法，并保留现有认证头和 abort signal。

**验证**

- 运行 `tests/unit/app/wplus_sop/test_router.py` 的产物读取测试。
- 运行 `console/src/api/modules/wplusSop.test.ts`。

### U3：先定义工作台页面预览行为

**文件**

- `console/src/pages/WPlusSopWorkspace/index.test.tsx`

**工作**

- 新增失败测试：阶段最新版本默认可在 JSON / Markdown / HTML 间切换并看到内容。
- 新增失败测试：切换历史版本后读取对应版本，确认按钮仍只绑定最新版本。
- 新增失败测试：累计预览读取指定 `preview_version`；加载失败显示可见错误且下载仍可重试。
- 新增回归测试：最终结果继续在页面内预览，并通过认证 API 读取。

**验证**

- RED：当前按钮列表实现无法满足内容断言。
- GREEN：U4 完成后工作台测试通过。

### U4：实现统一的三格式页面预览

**文件**

- `console/src/pages/WPlusSopWorkspace/index.tsx`
- `console/src/pages/WPlusSopWorkspace/index.module.less`
- `console/src/api/types/wplusSop.ts`

**工作**

- 提取阶段、累计、最终共用的三格式预览组件和加载状态。
- 默认选择 HTML；缺少 HTML 时按 Markdown、JSON 降级。
- JSON 解析成功时格式化，解析失败时原样显示并标记加载内容不可格式化。
- HTML 使用 `sandbox` iframe；加载、空、失败、重试状态不依赖颜色表达。
- 阶段版本选择使用稳定的 `(revision, report_no)` 身份；历史版本明确只读。
- 下载 loading key 包含产物完整身份，避免 v1/v2 同时显示 loading。

**验证**

- 工作台完整 Vitest 文件通过。
- TypeScript build/typecheck 通过。
- Prettier/ESLint 仅针对受影响文件或项目既有命令验证。

### U5：文档、回归与提交检查

**文件**

- `CONTEXT.md`
- `docs/superpowers/specs/2026-08-21-wplus-stage-incremental-artifacts-design.md`

**工作**

- 保持 Stage Report、Cumulative Preview 与最终 Result Bundle 的术语边界一致。
- 运行 GitNexus 变更检测，确认只影响预期 W+ 路由和工作台流程。
- 对优化提交执行独立规格、正确性、前端、安全和简化审查，修复重要问题后复验。

## 最终验证

- `venv` 对应 Python：产物路由聚焦 pytest。
- `console/node_modules/.bin/vitest`：API 与 W+ 工作台测试。
- `console/node_modules/.bin/tsc -b --noEmit`。
- `git diff --check`。
- `npx gitnexus detect-changes -r <repo> -s all`。

## 已知基线限制

- 优化前提交 `48f1b12ac` 的新增脚本测试因本地 Miner 脚本缺失而无法收集；其余聚焦后端仍有 8 个既有失败。本任务不会把这些与页面预览修复混在一起，但最终报告必须继续列明。
- 无关的 `docs/superpowers/specs/2026-08-21-agent-safety-governance-overall-design.md` 保持未提交，不纳入本任务。
