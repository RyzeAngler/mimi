# 贡献指南

感谢参与 Mimi。项目当前是硬件原型，修改时请保持固件、Agent、设备协议和操作手册的一致性。

## 提交前检查

```bash
cd /path/to/mimi/agent
python -m pytest -q

cd /path/to/mimi
platformio run --environment esp32-c3-supermini
```

不要提交：

- `agent/.env`；
- `firmware/config/network_secrets.h`；
- `.pio/`、`.pio-core/`、`.venv/`；
- `agent/cache/`、`agent/logs/`、Python 缓存；
- API Key、Wi-Fi 密码、局域网地址截图或运行日志。

新增或修改设备消息时，必须同时更新：

- `docs/protocol.md`；
- Agent 协议测试；
- 固件/Agent 的对应实现；
- `docs/操作手册.md` 的验收步骤。

## 代码原则

- 保持模块边界清晰；
- 优先使用明确的状态和数据结构；
- 不用固定文案掩盖外部服务错误；
- 硬件行为必须可通过串口日志观察；
- 代码和文档中的路径使用相对链接，避免写入个人机器信息。

项目采用 [MIT License](LICENSE)。
