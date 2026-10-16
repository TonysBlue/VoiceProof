# 任务8内部交付验证

工程源提交：`0048a88`；产品决策先行提交：`fbd5188`。正式仓 origin 为 `git@github.com:TonysBlue/VoiceProof.git`，分支 `task/8`。本记录是内部工程证据，不是独立验收、需求验证或发布许可。运行器已加载 generation-3 的仓库与任务上下文；任务远程推送依用户约束由可信运行器在连续性与交付验证后执行，本代理未运行 git push。

## 已验证的交付

同一正式仓增加本机桌面优先 Web、双击入口与安装后启动入口，直接复用原文本对齐和 WAV 音质内核。普通用户在页面内选择媒体、贴入或导入原稿、选填术语，获得本地自动转写、时间点问题卡、可点击回听与逐项复核；不用命令行、转写文件或 JSON。环境与文件关联需内部维护人员预先配置，尚无消费级独立安装包。

- `unit-tests.txt`：`PATH="$PWD/.runtime/bin:$PATH" python3.11 -m unittest discover -s tests -v`，23项通过，0失败、0跳过。Python3.11原环境缺失，经工作区 uv 安装3.11.17；没有使用 sudo 修改系统。包含原CLI回归、代表性文本场景、真实解码、真实独立worker坏媒体错误、HTTP上传、同源/令牌、范围回听、取消删除、闲置/超时、超限与模型缺失检查。
- 原稿/识别对共8个人工合成场景，3个干净/归一化样本候选误报为0，全部场景未经确认的“必须重录”为0；另有繁简归一化与模型拆词回归。JSON只作为内部评测夹具，消费者页面无需接触。测试超时用时钟偏移，上传限制用缩小阈值；不伪称经历了15分钟真实超时或100MB压力测试。
- WAV 合成语音通过真实 PyAV 解码；MP3/M4A/带画面MP4/FLAC通过本地生成与实际解码。UI端到端实际输入 WAV 与 MP4，未注入转写。MOV/WebM/OGG列在支持格式中，但未逐种完成本次容器兼容矩阵，异常会给重新导出提示。
- `browser-results.json`：Chromium headless 141，完整流程16.84秒。验证实际回听进度、确认后“必须重录”、全部忽略后“可忽略”、导出文本、清空后临时目录不存在、坏MP4中文恢复路径、390px布局无横向溢出；前端异常0、观察到的浏览器外部请求0。
- `desktop-input.png` / `desktop-review.png` / `failure.png` / `mobile-layout.png` 是真实页面截图。截图“确认有问题”是自动化模拟点击，用来验证结论计算，不代表有人听后确认该口播有错。浏览器导出的文本同理。
- `environment.json`：本机状态请求5.686ms（单次观测，不是分位数SLA）。模型权重哈希与实际依赖版本可追溯。媒体、原稿与转写不写入仓库；证据中的素材和识别内容全部来自可追溯的机器合成夹具。
- 安装命令 `uv pip install --python .runtime/bin/python -e '.[local]' --no-deps` 成功；明确仅打包voiceproof，避免把evidence作为命名空间包；静态资源加入包数据。`node --check voiceproof/static/app.js` 与 `git diff --check` 均通过。

## 真实模型观测与质量边界

`asr-results.json` 是固定 small 模型 revision `536b0662742c02347bc0e980a01041f333bce120` 的真实CPU转写，不是桩结果。15.529秒eSpeak NG合成普通话处理4.801秒，繁简及保守数字归一化后的token序列相似度0.775；这是单一合成样本诊断指标，不是CER/WER或真实用户准确率。产生4个候选问题（3个识别文本差异、1个疑似削波），自动要求重录为0。实际发现“录音/露营”等误识别，因此不能声称人声低误报门槛已经达成。

真实引擎测试促成了两个修复：合并模型数字/英文拆词的时间区间；本地OpenCC繁简归一化同时保留原始转写。合成器最初的cmn模式误把词典拼音按英文读出，已改为cmn-latn-pinyin并固定提交该音频；最终证据只报告修正后的夹具。没有修改原稿去迎合ASR结果。

识别worker显式离线、禁止Hub遥测，模型下载另走用户点击的安装任务。首次下载模型已用同一Hub下载接口完成；`model-cache-setup.json`还验证正式安装worker离线复用模型成功。本次未完整验证国内网络上的首次GUI下载、断点续传、安装超时恢复与跨系统首次安装。浏览器无外部请求不等于做过整机网络抓包审计。

临时目录700权限、本机回环服务、Host/Origin/随机令牌防护、无数据库、无外部素材接口。清空和正常退出删除；闲置30分钟、处理15分钟限制有自动清理。强制杀进程或断电可能留下系统临时目录；需维护人员清理。未验证Windows/macOS清理与浏览器兼容，不保证所有隐私场景。

## 复现

按README安装已验证依赖。真实模型测试不加入默认单元测试，以避免测试过程偷偷下载模型：

```bash
HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 python3.11 scripts/evaluate_asr.py --model /path/to/small --output evidence/task-8/asr-results.json
python3.11 -m pip install playwright==1.56.0
python3.11 -m playwright install chromium-headless-shell
python3.11 scripts/verify_browser.py --model /path/to/small --output evidence/task-8
```

本环境 `/tmp` 为只读，浏览器安装与验证使用工作区 `.tools/tmp` 作为TMPDIR；为截图额外从Ubuntu包提取文泉驿字体，通过工作区FONTCONFIG_FILE引用。未改系统或引入产品的外部字体依赖。

## 交接及尚未满足的验收

1. 可信运行器需校验CONTINUITY与MANIFEST后推送 `task/8`，并记录远程commit；远程交付尚未由本代理观测。
2. CEO需审阅首发推荐/体验合同。公共Product Engineer章程仍写PixWeave，与本任务指定VoiceProof存在名称陈旧，已在连续性记录上报；本代理仅修改指定VoiceProof仓。
3. 任务9场景交接未收到。本次场景是工程假设与合成夹具，不能冒充客户/需求证据。
4. Independent Quality Reviewer需独立验收。真实人声误报/召回、国内网络与目标机器性能、全格式/跨系统兼容、消费级无命令行安装包仍待验证。未以“全部测试绿”替代这些产品质量结论。
5. 没有发布、收费、客户联系、真实客户数据处理或法律承诺。下一步测试只能使用合成或已获准内部材料；任何外部行动继续受董事长授权约束。
