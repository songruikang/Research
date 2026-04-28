# 公司云主机部署完整约束

> 本文档记录了所有在公司环境部署 WrenAI 时踩过的坑和最终解法。
> 每一条都是真实遇到并解决的，不是理论推测。

---

## 1. 网络架构

```
宿主机 (7.182.9.1)
├── cntlm 代理: 127.0.0.1:3128 → 上游代理 10.0.0.41:8080 / 10.0.0.42:8080
├── socat 转发: 172.20.0.1:3128 → 127.0.0.1:3128 (systemd 服务自动运行)
├── Ollama GPU: 10.220.239.55:11434 (内网直通)
├── GitHub SSH: ssh.github.com:443 + ProxyCommand nc 代理
└── Docker 网段: 172.20.0.0/16, 172.21.0.0/16 (避开代理路由 172.18.215.0/24)
```

### 为什么 Docker 网段是 172.20 不是默认 172.17？

Docker 默认使用 172.17.0.0/16 和 172.18.0.0/16。但公司代理服务器在 172.18.215.0/24 网段，
Docker 的 172.18.0.0/16 桥接网络会覆盖这个路由，导致代理完全不通。
通过 daemon.json 把 Docker 网段限制在 172.20-172.21 解决。

### 为什么需要 socat？

cntlm 只监听 127.0.0.1:3128。Docker 容器通过桥接网关 172.20.0.1 访问宿主机，
到不了 127.0.0.1。socat 在 172.20.0.1:3128 开一个转发口，把流量转到 cntlm。

### 代理路由（systemd 服务自动恢复）

```bash
route add -net 172.18.215.0 netmask 255.255.255.0 gw 7.182.8.1 dev eth0
```

---

## 2. 关键配置文件（宿主机上的，不在 Git 里）

### /etc/docker/daemon.json
```json
{
  "default-address-pools": [
    {"base": "172.20.0.0/16", "size": 24},
    {"base": "172.21.0.0/16", "size": 24}
  ]
}
```

### /root/.docker/config.json
```json
{
  "proxies": {
    "default": {
      "httpProxy": "http://172.20.0.1:3128",
      "httpsProxy": "http://172.20.0.1:3128",
      "noProxy": "localhost,127.0.0.1,10.220.239.55,wren-engine,wren-ui,wren-ai-service,ibis-server,qdrant,chart-engine,172.20.0.0/16,172.21.0.0/16"
    }
  }
}
```
注意：noProxy 必须包含所有 Docker 服务名和 Ollama IP。

### systemd 服务
- `socat-docker-proxy.service` — 172.20.0.1:3128 → 127.0.0.1:3128 转发
- `docker-network-fix.service` — 恢复代理路由 + iptables FORWARD ACCEPT

---

## 3. Docker 构建规则

```bash
# 必须 DOCKER_BUILDKIT=0（BuildKit 在代理环境下有 exec format error）
# 必须通过 build-arg 传代理
DOCKER_BUILDKIT=0 docker build \
  --build-arg HTTP_PROXY=http://172.20.0.1:3128 \
  --build-arg HTTPS_PROXY=http://172.20.0.1:3128 \
  -t <image-name>:latest \
  -f <Dockerfile.cloud> .
```

### 为什么不用 BuildKit？
BuildKit 拉取基础镜像 metadata 时走独立网络栈，代理配置不生效，导致超时。

### 为什么不用 compose build？
`docker compose build` 内部仍会尝试 BuildKit/Bake。直接 `docker build` 最可控。
compose 只负责启动：`docker compose up -d --no-build --pull never`

### PLATFORM 必须匹配
- Mac: `PLATFORM=linux/arm64`
- 云主机: `PLATFORM=linux/amd64`

---

## 4. Dockerfile.cloud 特殊处理

### wren-ui/Dockerfile.cloud
- 禁用 corepack（SSL 中间人导致联网失败）
- 本地 yarn wrapper（node .yarn/releases/yarn-4.5.3.cjs）
- COPY node_modules（宿主机预装后直接拷入，.dockerignore 里 node_modules 不能被排除）
- NODE_TLS_REJECT_UNAUTHORIZED=0

### wren-ai-service/docker/Dockerfile.cloud
- 两阶段都需要代理 build-arg
- apt 用小写 http_proxy
- 安装 netcat-openbsd（entrypoint.sh 健康检查）
- 降级 qdrant-client==1.12.1

### chart-engine/Dockerfile
- 无 cloud 版本（依赖全是 pip install，不需要代理特殊处理）
- 但构建时仍需传 HTTP_PROXY（pip install 走外网）

---

## 5. wren-ui node_modules 预装流程

```bash
cd wren-ui

docker run --rm \
  --network host \
  -v $(pwd):/app -w /app \
  -e NODE_TLS_REJECT_UNAUTHORIZED=0 \
  node:18-bookworm-slim \
  sh -c '
    node .yarn/releases/yarn-4.5.3.cjs config set httpProxy http://127.0.0.1:3128 && \
    node .yarn/releases/yarn-4.5.3.cjs config set httpsProxy http://127.0.0.1:3128 && \
    node .yarn/releases/yarn-4.5.3.cjs config set enableStrictSsl false && \
    node .yarn/releases/yarn-4.5.3.cjs install
  '
```

### 什么时候需要重新装？
- git pull 后 package.json/yarn.lock 有变化
- Claude Code 在 Mac 上添加了新依赖（commit message 会标注）

---

## 6. 部署脚本

统一使用 `Research/deploy.sh`：

```bash
bash deploy.sh build [ui|ai|chart|all]   # 构建镜像
bash deploy.sh up                         # 启动服务
bash deploy.sh rebuild [ui|ai|chart|all]  # 构建+重启
bash deploy.sh logs [ui|ai|chart]         # 查看日志
bash deploy.sh check                      # 网络诊断
bash deploy.sh status                     # 服务状态
```

### git pull 后的标准流程

```bash
cd /opt/ruikang/code/github/Research
git pull

# 1. 看 commit message 是否有新依赖
# 2. 有新 npm 依赖 → 重新装 node_modules（见第 5 节）
# 3. 有新 Python 依赖 → rebuild ai
# 4. 只改了前端 → rebuild ui
# 5. 只改了 chart-engine → rebuild chart
# 6. 最安全方式 → rebuild all
```

---

## 7. 故障排查

### 代理不通
```bash
systemctl status cntlm
nc -zv 10.0.0.41 8080 -w 3
ip route show | grep 172.18.215
```

### Docker 容器间通信失败
```bash
cat /root/.docker/config.json | python3 -m json.tool  # 检查 noProxy
iptables -L FORWARD -n | head -3                       # 检查 FORWARD
```

### 构建时 exec format error
```bash
grep PLATFORM docker/.env  # 确认 linux/amd64
```

### wren-ui 构建失败 prettier/eslint 报错
Mac 上提交前必须 `npx prettier --write <file>` + `yarn check-types`。
