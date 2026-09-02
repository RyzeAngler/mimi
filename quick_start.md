# Mimi 快速开始

本文只覆盖“能编译、能烧录、能看到设备启动”的最短路径。完整接线、Agent 启动顺序、语音链路和故障排查请看 [完整操作手册](docs/操作手册.md)。

## 1. 准备工具

- VS Code + PlatformIO IDE；
- 可传输数据的 USB 数据线；
- ESP32-C3 SuperMini；
- Python 3.11 或更高版本（启动 Agent 时需要）。

PlatformIO CLI 可选。如果终端提示 `command not found`，先执行：

```bash
export PATH="$HOME/.platformio/penv/bin:$PATH"
platformio --version
```

也可以直接在 VS Code 的 PlatformIO 面板执行 Build、Upload 和 Monitor，不要求终端存在 `pio` 命令。

## 2. 编译固件

```bash
cd /path/to/mimi
platformio run --environment esp32-c3-supermini
```

首次构建会下载 ESP32 平台、Arduino 框架和库，耗时较长属于正常现象。

## 3. 查询串口并烧录

插入开发板后：

```bash
platformio device list
```

记录类似 `/dev/cu.usbmodemXXXX` 的设备路径，然后执行：

```bash
platformio run --target upload \
  --environment esp32-c3-supermini \
  --upload-port /dev/cu.usbmodemXXXX
```

如果设备没有出现，按住 BOOT，按一下 RESET，先松开 RESET，再松开 BOOT，然后重新查询串口。

## 4. 查看固件日志

```bash
platformio device monitor \
  --port /dev/cu.usbmodemXXXX \
  --baud 115200
```

启动成功应看到：

```text
Mimi firmware booting
I2C scan started
TTP223 ready: SIG=GPIO10 active=HIGH debounce=50ms
I2S player ready: BCLK=6 LRCLK=7 DOUT=21
Mimi firmware ready
heartbeat: 1
```

如果接好了 OLED 和 MPU6050，还应看到：

```text
I2C device found at 0x3C
I2C device found at 0x68
OLED ready at 0x3C
MPU6050 ready at 0x68, WHO_AM_I=0x68
```

## 5. 启动 Agent

完整语音闭环需要先启动 Python Agent：

```bash
cd /path/to/mimi/agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

编辑 `agent/.env`，填写：

```env
ARK_API_KEY=
ARK_MODEL=doubao-seed-2-0-mini-260428
VOLCENGINE_API_KEY=
VOLCENGINE_RESOURCE_ID=
VOLCENGINE_VOICE_TYPE=
```

然后启动：

```bash
PYTHONPATH=src python -m mimi_agent.application.server
```

服务启动成功应看到类似：

```text
Mimi Agent 已启动，监听 ws://0.0.0.0:8765
```

保持这个终端运行。另开一个终端重新烧录或按 RESET，让 ESP32 连接 Agent。

## 6. 最小验收顺序

1. 串口看到 `Mimi firmware ready`；
2. OLED 显示默认眼睛；
3. 水平放置，默认表情每 5 秒进行一次友好眨眼；
4. 左右倾斜，眼睛跟随方向；
5. 触摸 TTP223，看到 `touch: pressed`；
6. Agent 在线时，串口出现 `Agent WebSocket connected`；
7. 触摸或晃动后，依次看到 `motion_ack`、`Speech start`、`Speech end`、`reaction playback complete`；
8. MAX98357A 和扬声器输出语音。

## 7. 停止

- Agent：在 Agent 终端按 `Ctrl+C`；
- 串口监视器：按 `Ctrl+C`；
- ESP32：拔掉 USB 或按 RESET 重启。

下一步请按 [docs/操作手册.md](docs/操作手册.md) 完成接线和问题排查。
