# 项目协作规则

> 本文件每次对话自动加载。这里的规则是从历史协作中提炼的硬性要求，不是建议。

## 用户画像

6 年后端工程师，架构/CI 强，前端基础。工作风格：先讨论方案再动手，对细节敏感，不容忍低级错误。双环境开发：Mac（Claude Code）+ 公司 Ubuntu 云（部署/评测）。中文沟通。

## 双环境硬约束（必读）

> Mac 上写的每一行代码，最终都要能在公司云主机上跑。详细约束见 `DEPLOY_CONSTRAINTS.md`。

### 绝对禁止

1. **不要修改 Dockerfile.cloud** — 云主机专用，经过大量踩坑才稳定。如需改动必须先说明原因。
2. **不要把 .env / config.yaml 提交到 Git** — 只提交 `.example` / `.cloud` / `.mac` 模板。
3. **不要在 .dockerignore 里排除 node_modules** — 云主机用"宿主机预装 + COPY 进容器"策略。
4. **不要用 corepack** — 云主机代理 SSL 中间人导致 corepack 必定失败。
5. **不要假设网络正常** — 云主机在公司防火墙后，所有外网访问需走代理。

### 双环境文件对照表

| 用途 | Mac | 公司云 |
|------|-----|--------|
| Docker Compose | `docker/docker-compose.yaml` | `docker/docker-compose-dev.yaml` |
| 部署脚本 | 直接 `docker compose up -d` | `bash deploy.sh rebuild all` |
| wren-ui Dockerfile | `wren-ui/Dockerfile` | `wren-ui/Dockerfile.cloud`（不要改） |
| wren-ai-service Dockerfile | `docker/Dockerfile` | `docker/Dockerfile.cloud`（不要改） |
| 环境变量模板 | `docker/.env`（Mac 本地） | `docker/.env.cloud` → `cp` 为 `.env` |
| PLATFORM | `linux/arm64` | `linux/amd64` |
| 构建方式 | BuildKit 正常 | 必须 `DOCKER_BUILDKIT=0` |

### 改 Docker 相关文件时的检查清单

**每次涉及 docker/ 目录的改动，必须同步以下所有文件：**

- [ ] `docker-compose.yaml` — Mac
- [ ] `docker-compose-dev.yaml` — 公司云
- [ ] `deploy.sh`（Research 根目录） — 构建脚本（新增服务要加 build 步骤）
- [ ] `.env` + `.env.cloud` — 环境变量

### 添加新 npm 依赖时

1. `yarn add <pkg>` 更新 package.json + yarn.lock
2. **commit message 明确标注新增了哪些依赖**
3. 云主机部署前需重新执行 node_modules 安装（见 `DEPLOY_CONSTRAINTS.md` 第 5 节）

### 修改前端文件时

- 必须 `npx prettier --write <file>` + `yarn check-types` 通过
- 云主机 `yarn build` 会 lint，格式错误导致构建失败

### 新建目录/模块时

- 测试文件跟源码放一起或统一在项目级 `tests/` 下，不要散落在外层
- 生成的输出目录必须 `.gitignore`，必须在 AGENTS.md 说明生成命令
- 目录结构要分级（core/server/cli/utils），不要一级平铺十几个文件

## 工作流：四个阶段 x 检查点

### 阶段一：设计（多聊）

- 用户给方向，我出 2-3 个具体方案，推荐一个并说明理由
- 有不同意见直接说，不附和。拼写/术语错误要纠正
- 待排查/支线任务写 TODO 文档，不写 memory
- 确认方案后再动手，不要边做边问
- **设计阶段就要考虑双环境兼容、目录结构、生成物位置**

### 阶段二：执行（自闭环）

**写代码前必须做：**
- [ ] 读相关模块的 AGENTS.md，了解现有结构和约定
- [ ] 读 `DEPLOY_CONSTRAINTS.md`，确认双环境兼容
- [ ] 文件名/函数名自问："用户看名字能理解它做什么吗？"

**写代码时必须做：**
- [ ] 不硬编码环境信息（URL/端口/路径），走参数或配置
- [ ] 改了函数签名/返回值，顺着调用链检查所有调用方
- [ ] 预判目标模型的行为差异（Qwen 有 think 标签、不同 API 格式）
- [ ] 注释说"为什么"，不说"是什么"
- [ ] 废弃文件/代码立即删除，不留着

**写完代码后必须做：**
- [ ] 跑脚本验证能用（不是"应该能用"）
- [ ] 同步更新 AGENTS.md / 说明文档
- [ ] 如果是 sub-agent 并行任务，用 background 模式让用户看到进度

### 阶段三：交付（一次到位）

用户说"检查"或"提交"时，**一次性完成以下全部检查**，不要分多轮：

- [ ] `git status` — 确认改动范围，有无遗漏/多余文件
- [ ] 目录结构 — 文件在正确位置，命名与功能一致，没有散落的临时目录
- [ ] 文件头描述 — docstring/注释与实际功能一致
- [ ] AGENTS.md — 所有引用路径、脚本名、IO 描述与代码同步
- [ ] 双环境检查 — docker-compose.yaml 和 docker-compose-dev.yaml 同步、deploy.sh 覆盖新服务
- [ ] 前端 prettier — `npx prettier --write` + `yarn check-types` 通过
- [ ] 跑测试 — 关键脚本 end-to-end 验证通过
- [ ] 确认完毕后告诉用户："已检查完毕，准备提交"

### 阶段四：提交（等指令）

- 不主动 commit/push，等用户明确说
- 操作前 `git fetch` 检查远端状态
- 一个完整任务一个 commit，commit message 说清楚改了什么和为什么
- **新增依赖必须在 commit message 中标注**
- 推送前确认目标分支（main / feature branch）

## 文档规则

- 功能模块变更 → 同步更新该模块 AGENTS.md
- 用户说晚安 → 写当日总结到 `docs/daily/YYYY-MM-DD.md`
- 生成的文件 → 在文档说明怎么生成（输入/命令/输出）
- 时间戳格式：`YYYY-MM-DD HH:MM`，不加时区后缀
