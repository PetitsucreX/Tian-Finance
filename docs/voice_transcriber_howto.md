# 语音/视频逐字稿小程序（voice_transcriber）

在 macOS 上，从「照片」App（含 iCloud 同步的视频）或任意文件夹里找出带人声的录音/视频，
用本地 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 把语音**一字不漏**地转成逐字稿。
全程在你电脑本地运行，音频不上传云端。支持自动识别**法语 / 中文 / 英语**等语种。

## 一、安装（只需一次）

```bash
# 1. 系统依赖：ffmpeg（抽音轨用）
brew install ffmpeg

# 2. Python 依赖（在仓库根目录）
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[transcriber]"
```

> `faster-whisper` 首次使用某个模型时会自动下载模型文件（`large-v3` 约 1.5 GB），
> 之后会缓存复用。Apple Silicon 用 CPU 即可，建议加 `--compute-type int8` 提速。

第一次在「照片」库上运行时，macOS 会弹窗请求**「完全磁盘访问权限」**，
给运行的终端（Terminal / iTerm）勾选授权即可。

## 二、三步用法

### 1. 先看看相册里有哪些语音视频

```bash
voice-transcriber find --detect-speech
```

- 默认读取「照片」App 资料库，只看视频，并用 VAD 检测哪些**真的有人声**。
- 常用过滤：`--since 2026-01-01 --until 2026-03-31`、`--include-audio`（也含纯音频）。
- 不想动照片库？扫描某个文件夹：
  ```bash
  voice-transcriber find --source folder --folder ~/Desktop/录音 --detect-speech
  ```

### 2. 生成逐字稿

```bash
# 对相册里所有“有语音”的视频批量转写
voice-transcriber transcribe --output-dir ~/Desktop/逐字稿

# 或者只转写你手上某几个文件
voice-transcriber transcribe ~/Movies/clip1.mov ~/Movies/clip2.mov
```

### 3. 取走结果

逐字稿默认写到 `transcripts/`（或 `--output-dir`），每个视频对应：

- `xxx.txt` —— 纯逐字稿全文（你要的「一字不错」的逐字稿）。
- `xxx.md` —— 带标题、全文 + 时间轴，方便阅读核对。

需要别的格式：`--format txt md srt vtt json`（可多选，`srt/vtt` 是字幕）。

## 三、常用参数

| 参数 | 作用 | 默认 |
| --- | --- | --- |
| `--source photos\|folder` | 数据来源 | `photos` |
| `--folder PATH` | 文件夹模式扫描目录 | — |
| `--language fr\|zh\|en\|auto` | 指定语言，`auto` 自动识别 | `auto` |
| `--model` | Whisper 模型 | `large-v3` |
| `--compute-type int8` | CPU 提速（精度略降） | `auto` |
| `--prompt "专有名词,人名"` | 提示词，提升术语准确度 | — |
| `--since / --until` | 按日期过滤 | — |

## 四、关于「一字不错」

- 默认用最大的 `large-v3` 模型 + beam search（`--beam-size 5`），中文/法语准确度最佳。
- 转写**不做任何改写或润色**，逐段保留原话；只丢弃 VAD 判定为静音的空段。
- 若有专有名词（公司名、人名、产品名），用 `--prompt` 喂进去能显著减少错别字。
- 机器转写仍可能有个别误差；`xxx.md` 带时间轴，方便你对照原视频快速校对。

## 五、架构

```
src/voice_transcriber/
  photos.py      # 从「照片」库(osxphotos)或文件夹发现录音/视频
  audio.py       # ffprobe 探测、ffmpeg 抽 16kHz 单声道音轨、VAD 语音检测
  transcribe.py  # faster-whisper 逐字转写（惰性加载模型）
  formats.py     # 输出 txt / md / srt / vtt / json
  cli.py         # 命令行入口（find / transcribe）
```

重型依赖（`osxphotos`、`faster-whisper`、`ffmpeg`）都是**惰性加载**，
所以在没装这些库的机器上也能 `import` 包并运行单元测试。
