#!/usr/bin/env bash
# 启动到 6403 服务器的 SSH 隧道，把本地 8001 端口转发到服务器内 vLLM emotion 实例。
# 用法：bash scripts/start_emotion_tunnel.sh
# 中断：Ctrl+C 或 kill $(lsof -t -i:8001)
#
# 服务器侧 vLLM 进程（容器内）：
#   vllm serve /app/emotion_model --port 8001 --served-model-name qwen3.5-9b-emotion
# 模型：Qwen3.5-9B + emotion3 LoRA（merge），3 分类（positive/negative/neutral）。

set -euo pipefail

REMOTE_HOST="lvshuyang@172.17.43.38"
# 本地端口：8001 在共享开发机上常被其他服务占用（scholartrace-mc 等），
# 默认改用 28111。如需改回可通过环境变量覆盖。
LOCAL_PORT="${EMOTION_TUNNEL_LOCAL_PORT:-28111}"
# 远程目标：vLLM 跑在 smarttutor-final 容器内，bridge 网络下 IP 一般是
# 172.18.0.2；容器重建后 IP 可能变化，重跑 docker inspect 确认。
REMOTE_TARGET="${EMOTION_TUNNEL_REMOTE_TARGET:-172.18.0.2:8001}"

echo "[emotion-tunnel] localhost:${LOCAL_PORT} -> ${REMOTE_HOST}:${REMOTE_TARGET}"
echo "[emotion-tunnel] Ctrl+C to stop"

# -N: 不执行远程命令；-T: 不分配 tty；ServerAliveInterval 保持长连接
exec ssh -N -T \
  -L "${LOCAL_PORT}:${REMOTE_TARGET}" \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  "$REMOTE_HOST"
