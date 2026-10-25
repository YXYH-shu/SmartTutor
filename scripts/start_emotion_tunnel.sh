#!/usr/bin/env bash
# 启动到 6403 服务器的 SSH 隧道，转发两个 vLLM 服务：
#   28110 -> 127.0.0.1:8100  主模型 qwen3.5-35b-a3b（通用 agent 用）
#   28111 -> 127.0.0.1:8101  情感模型 qwen3.5-9b-emotion（emotion_analyzer 用）
# 用法：bash scripts/start_emotion_tunnel.sh    （中断：Ctrl+C）
# 8100/8101 对外部源地址不可达（仅 22 端口稳定），必须走本隧道。

set -euo pipefail

# 走 ~/.ssh/config 的 6403 别名（zhanghaonan + id_ed25519）；lvshuyang 账号不支持本机公钥
REMOTE_HOST="${EMOTION_TUNNEL_REMOTE_HOST:-6403}"
MAIN_LOCAL_PORT="${MAIN_TUNNEL_LOCAL_PORT:-28110}"
MAIN_REMOTE_TARGET="${MAIN_TUNNEL_REMOTE_TARGET:-127.0.0.1:8100}"
EMOTION_LOCAL_PORT="${EMOTION_TUNNEL_LOCAL_PORT:-28111}"
EMOTION_REMOTE_TARGET="${EMOTION_TUNNEL_REMOTE_TARGET:-127.0.0.1:8101}"

echo "[model-tunnels] localhost:${MAIN_LOCAL_PORT} -> ${REMOTE_HOST}:${MAIN_REMOTE_TARGET} (qwen3.5-35b-a3b)"
echo "[model-tunnels] localhost:${EMOTION_LOCAL_PORT} -> ${REMOTE_HOST}:${EMOTION_REMOTE_TARGET} (qwen3.5-9b-emotion)"
echo "[model-tunnels] Ctrl+C to stop"

# -N: 不执行远程命令；-T: 不分配 tty；ServerAliveInterval 保持长连接
exec ssh -N -T \
  -L "${MAIN_LOCAL_PORT}:${MAIN_REMOTE_TARGET}" \
  -L "${EMOTION_LOCAL_PORT}:${EMOTION_REMOTE_TARGET}" \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  "$REMOTE_HOST"
