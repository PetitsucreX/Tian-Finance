# 语音/视频逐字稿小程序（voice_transcriber）

在 macOS 上把录音/视频里的语音**一字不漏**地转成逐字稿。全程本地运行（用
[faster-whisper](https://github.com/SYSTRAN/faster-whisper)），音频不上传云端，
自动识别**法语 / 中文 / 英语**等语种。

数据来源支持三种：
- **语音备忘录**（`--source voicememos`）—— iPhone「语音备忘录」App 的录音，经 iCloud 同步到 Mac。
- **文件夹**（`--source folder`）—— 任意目录，最省事的兜底方案。
- **照片库**（`--source photos`）—— 「照片」App 里的视频。

> 你的场景是 iPhone 语音备忘录里的几段录音，并希望**从手机一键触发 Mac 转写**。
> 直接看下面的「三、从手机一键命令 MacBook」。

## 一、安装（只需一次）

```bash
brew install ffmpeg                     # 抽音轨用
cd ~/Tian-Finance
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[transcriber]"
```

> 首次用某个模型会自动下载（`large-v3` 约 1.5 GB）后缓存。Apple Silicon 用 CPU 即可，
> 建议 `--compute-type int8` 提速。

## 二、语音备忘录在 Mac 上吗？（先确认同步）

语音备忘录要在 Mac 上能读到，需要 **iCloud 同步已打开**：

- **iPhone**：设置 →（你的 Apple ID）→ iCloud → 把「语音备忘录」打开。
- **Mac**：系统设置 →（你的 Apple ID）→ iCloud → 把「语音备忘录」打开。
- 两台设备登录**同一个 Apple ID**。打开后，Mac 上的「语音备忘录」App 里就能看到这些录音。

确认是否已同步，最简单的办法是先列一下：

```bash
voice-transcriber find --source voicememos
```

- 列出来了 → 已同步，直接进第 3 步转写。
- 报「找不到语音备忘录目录」→ 还没同步。两个办法二选一：
  1. 按上面打开 iCloud 同步，等几分钟让它同步下来；或
  2. **不依赖同步**：在 iPhone「语音备忘录」里选中那几段，分享 → **AirDrop 到 Mac**，
     存进某个文件夹，然后用 `--source folder` 转（见下）。

### 转写语音备忘录

```bash
voice-transcriber transcribe --source voicememos \
    --output-dir ~/Desktop/逐字稿 --skip-existing
```

### 或者：AirDrop 到文件夹再转（不依赖同步）

```bash
voice-transcriber transcribe --source folder \
    --folder ~/Desktop/录音 --output-dir ~/Desktop/逐字稿
```

逐字稿默认输出每段一个 `.txt`（纯全文，即「一字不错」的逐字稿）和 `.md`（带时间轴便于核对）。
需要字幕等格式：`--format txt md srt vtt json`。

## 三、从手机一键命令 MacBook（核心需求）

思路：**iPhone 快捷指令** →「通过 SSH 运行脚本」→ 在 Mac 上跑转写脚本 →
逐字稿写入 **iCloud Drive** → 手机「文件」App 里立刻能看。可用 Siri 触发。

### 步骤 1：Mac 开启远程登录（SSH）

系统设置 → 通用 → 共享 → 打开「**远程登录**」。记下面板上显示的用户名和
Mac 的地址（局域网内形如 `用户名@192.168.x.x`，或 `用户名@你的Mac名.local`）。

### 步骤 2：Mac 上确认封装脚本可跑

仓库自带 `scripts/transcribe_voice_memos.sh`，它会转写所有语音备忘录并把逐字稿
写进 iCloud Drive 的 `VoiceMemo逐字稿` 文件夹（`--skip-existing`，可反复触发不重复转）。
先在 Mac 本机试一次：

```bash
bash ~/Tian-Finance/scripts/transcribe_voice_memos.sh
```

可用环境变量自定义：`VT_VENV`（venv 路径）、`VT_OUTPUT`（输出目录）、
`VT_MODEL`、`VT_COMPUTE`、`VT_LANGUAGE`。

### 步骤 3：iPhone 建一个快捷指令

打开「快捷指令」App → 新建 → 添加操作「**通过 SSH 运行脚本**」(Run Script Over SSH)：

- **主机/Host**：步骤 1 的地址（如 `192.168.1.20`）
- **用户/User**、**密码或 SSH 密钥**：你的 Mac 账户
- **脚本/Script**：
  ```bash
  bash ~/Tian-Finance/scripts/transcribe_voice_memos.sh
  ```

给它起名「转写语音备忘录」。以后在手机上点一下，或对 Siri 说「转写语音备忘录」即可。
跑完后，转写结果就在手机「文件」App → iCloud Drive → `VoiceMemo逐字稿` 里。

> 小贴士：手机和 Mac 不在同一局域网时，SSH 直连需要公网可达或 VPN；
> 日常用建议让两者在同一 Wi-Fi 下，最稳。

## 四、常用参数

| 参数 | 作用 | 默认 |
| --- | --- | --- |
| `--source photos\|folder\|voicememos` | 数据来源 | `photos` |
| `--folder PATH` | 文件夹模式扫描目录 | — |
| `--recordings-dir PATH` | 自定义语音备忘录目录 | 自动探测 |
| `--language fr\|zh\|en\|auto` | 指定语言，`auto` 自动识别 | `auto` |
| `--model` | Whisper 模型 | `large-v3` |
| `--compute-type int8` | CPU 提速（精度略降） | `auto` |
| `--skip-existing` | 跳过已转写的，反复触发不重复 | 关 |
| `--prompt "专有名词,人名"` | 提示词，提升术语准确度 | — |
| `--format txt md srt vtt json` | 输出格式（可多选） | `txt md` |
| `--since / --until` | 按日期过滤 | — |

## 五、关于「一字不错」

- 默认用最大的 `large-v3` 模型 + beam search（`--beam-size 5`），中文/法语准确度最佳。
- 转写**不做任何改写或润色**，逐段保留原话；只丢弃 VAD 判定为静音的空段。
- 有专有名词（公司名、人名）用 `--prompt` 喂进去能显著减少错别字。
- 机器转写仍可能有个别误差；`.md` 带时间轴，方便对照原录音快速校对。

## 六、架构

```
src/voice_transcriber/
  voicememos.py  # 读「语音备忘录」iCloud 目录(+CloudRecordings.db 取标题/日期)
  photos.py      # 从「照片」库(osxphotos)或文件夹发现录音/视频
  audio.py       # ffprobe 探测、ffmpeg 抽 16kHz 单声道音轨、VAD 语音检测
  transcribe.py  # faster-whisper 逐字转写（惰性加载模型）
  formats.py     # 输出 txt / md / srt / vtt / json
  cli.py         # 命令行入口（find / transcribe）
scripts/
  transcribe_voice_memos.sh   # 手机 SSH 一键触发的封装脚本
```

重型依赖（`osxphotos`、`faster-whisper`、`ffmpeg`）都是**惰性加载**，
所以在没装这些库的机器上也能 `import` 包并运行单元测试。
