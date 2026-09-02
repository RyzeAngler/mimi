# MiniCPM-V 4.6 本地部署测试手册

## 1. 目的

本手册用于在 macOS Apple Silicon 电脑上独立部署并测试面壁智能的 `MiniCPM-V 4.6` 视觉语言模型。

测试链路是：

```text
本地图片 + 文字问题
        ↓
MiniCPM-V 4.6
        ↓
本地 HTTP API 返回文本
```

本手册不会修改 Mimi Agent，也不会连接 ESP32。先确认模型本身可以稳定接收图片并输出文本，再进行 Mimi 的传感器、摄像头、VLM、TTS 联调。

## 2. 当前机器结论

当前机器是 Apple M1、8 GB 统一内存、ARM64。建议使用：

```text
MiniCPM-V 4.6
GGUF
Q4_K_M
llama.cpp
```

不要使用 `MiniCPM-o 4.5` 做本次测试。它是更大的全模态模型，面向实时语音/视频的官方建议配置高于当前机器。

MiniCPM-V 4.6 官方提供 GGUF 量化版本，并支持 llama.cpp、Ollama 等端侧推理框架；模型官方示例也使用 `Q4_K_M` 启动本地服务。[MiniCPM-V 4.6 官方模型仓库](https://huggingface.co/openbmb/MiniCPM-V-4.6-gguf)

## 3. 前置检查

在终端执行：

```bash
uname -m
system_profiler SPHardwareDataType | grep -E "Model Name|Chip|Memory"
brew --version
```

预期结果应包含：

```text
arm64
Chip: Apple M1
Memory: 8 GB
```

如果没有 Homebrew，请先安装 Homebrew，再继续后面的步骤。

## 4. 安装 llama.cpp

```bash
brew install llama.cpp
llama --version
```

如果安装完成后没有 `llama` 命令，执行：

```bash
which llama-server
llama-server --version
```

新版 llama.cpp 提供统一的 `llama serve` 命令；`llama-server` 是兼容的直接服务端命令。llama.cpp 的服务端提供 OpenAI-compatible API，并支持使用 `image_url` 传入远程图片或 Base64 图片。[llama.cpp 服务端文档](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)

## 5. 启动 MiniCPM-V 4.6

打开第一个终端窗口，执行：

```bash
llama serve \
  -hf openbmb/MiniCPM-V-4.6-gguf:Q4_K_M \
  --alias minicpm-v-4.6 \
  --host 127.0.0.1 \
  --port 8080 \
  --ctx-size 4096 \
  --parallel 1
```

第一次启动会下载模型和视觉相关文件，需要等待下载完成。服务启动后不要关闭这个终端。

这里将服务绑定到 `127.0.0.1`，只允许本机访问，不暴露到局域网。

如果 `llama serve` 不存在，可以使用：

```bash
llama-server \
  -hf openbmb/MiniCPM-V-4.6-gguf:Q4_K_M \
  --alias minicpm-v-4.6 \
  --host 127.0.0.1 \
  --port 8080 \
  --ctx-size 4096 \
  --parallel 1
```

## 6. 检查服务状态

打开第二个终端窗口，执行：

```bash
curl -fsS http://127.0.0.1:8080/health
```

服务完成加载后应返回类似：

```json
{"status":"ok"}
```

再检查模型名称：

```bash
curl -fsS http://127.0.0.1:8080/v1/models
```

返回 JSON 且包含 `minicpm-v-4.6`，说明本地服务已经可以接受 API 请求。

## 7. 使用远程测试图片验证视觉输入

执行下面的测试请求：

```bash
curl -sS \
  -w '\nrequest_time=%{time_total}s\n' \
  http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  --data-raw '{
    "model": "minicpm-v-4.6",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "text",
            "text": "请用一句中文说明图片中最明显的主体，不要猜测图片中没有明确显示的内容。"
          },
          {
            "type": "image_url",
            "image_url": {
              "url": "https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/p-blog/candy.JPG"
            }
          }
        ]
      }
    ],
    "max_tokens": 64,
    "temperature": 0
  }'
```

成功标准：

- HTTP 请求不是 4xx 或 5xx；
- 返回 JSON 中存在 `choices[0].message.content`；
- 返回内容确实基于图片，而不是只重复问题；
- 第一次请求完成后，后续请求耗时明显降低。

如果出现 `image input is not supported`，通常表示视觉投影文件没有加载成功，或者当前 llama.cpp 版本过旧。先升级：

```bash
brew upgrade llama.cpp
```

然后停止旧服务，再重新执行启动命令。

## 8. 使用本地 JPEG 验证真实图片

准备一张本地 JPEG，例如手机拍摄的桌面照片。不要直接使用包含隐私信息的照片进行首次测试。

```bash
IMAGE_PATH="/absolute/path/to/test.jpg"
IMAGE_B64="$(base64 < "$IMAGE_PATH" | tr -d '\n')"

curl -sS \
  -w '\nrequest_time=%{time_total}s\n' \
  http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  --data @- <<JSON
{
  "model": "minicpm-v-4.6",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "请客观描述这张照片中的人物、物体和整体场景。看不清的内容不要猜。"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/jpeg;base64,${IMAGE_B64}"
          }
        }
      ]
    }
  ],
  "max_tokens": 128,
  "temperature": 0
}
JSON
```

当前 Mimi 电脑摄像头的授权问题与本测试无关。只要能准备一张 JPEG，就可以先验证 MiniCPM-V 4.6 的视觉能力。

## 9. 简单性能测试

连续执行第 8 节的请求三次，记录每次的 `request_time`。

重点观察：

| 指标 | 观察内容 |
|---|---|
| 首次请求耗时 | 包含模型加载或视觉模块初始化的成本 |
| 后续请求耗时 | 模型已常驻内存时的响应速度 |
| 输出完整性 | 是否生成完整、可读的中文文本 |
| 内存压力 | 活动监视器中是否出现明显交换内存或系统卡顿 |
| 稳定性 | 连续 5 次请求是否出现崩溃或空响应 |

对于 M1 8 GB，不把 MiniCPM-V 4.6 当作每帧实时字幕模型。Mimi 后续应由轻量视觉检测持续处理画面，MiniCPM-V 只在动作事件或场景变化时分析关键帧。

## 10. Mimi 后续接入方式

本地模型验证通过后，Mimi 的目标链路应是：

```text
ESP32 motion_event + 本机摄像头关键帧
              ↓
     本地 MiniCPM-V 4.6
              ↓
       Mimi 回复文本
              ↓
       现有豆包 TTS
              ↓
       PCM → ESP32 播放
```

VLM 已经包含语言生成能力，因此原来的火山方舟 LLM 不需要作为主路径继续运行。Mimi 仍然需要保留传感器解析、事件过滤、冷却、打断、对话历史和 TTS 编排等确定性逻辑。

接入时需要在 Agent 中增加一个本地 VLM 客户端，将当前传感器 JSON 和图片组成 OpenAI-compatible 的 `messages`，请求地址指向：

```text
http://127.0.0.1:8080/v1
```

这属于下一阶段代码改动，本手册不执行该改动。

## 11. 停止服务

回到运行 llama.cpp 的第一个终端，按：

```text
Ctrl-C
```

模型文件会保留在本机缓存中，下次启动不需要重新下载。

## 12. 相关官方资料

- [MiniCPM-V 4.6 官方模型卡](https://huggingface.co/openbmb/MiniCPM-V-4.6)
- [MiniCPM-V 4.6 GGUF 官方模型仓库](https://huggingface.co/openbmb/MiniCPM-V-4.6-gguf)
- [OpenBMB MiniCPM 官方 GitHub](https://github.com/OpenBMB/MiniCPM-V)
- [llama.cpp 服务端 API 文档](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
