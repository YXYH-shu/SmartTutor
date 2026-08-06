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
LOCAL_PORT="${EMOTION_TUNNEL_LOCAL_PORT:-8001}"
REMOTE_PORT="${EMOTION_TUNNEL_REMOTE_PORT:-8001}"

echo "[emotion-tunnel] $LOCAL_PORT -> $REMOTE_HOST:$REMOTE_PORT"
echo "[emotion-tunnel] Ctrl+C to stop"

# -N: 不执行远程命令；-T: 不分配 tty；ServerAliveInterval 保持长连接
exec ssh -N -T \
  -L "${LOCAL_PORT}:localhost:${REMOTE_PORT}" \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  "$REMOTE_HOST"
