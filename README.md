# VoiceProof 声检

阶段 0 离线原型：把用户提供的原稿和转写文本对齐，标记疑似漏读、重复、替换、数字与术语差异；同时检查 PCM WAV 的静音和音量。结果是供用户复核的证据，不是“零错误”保证。

## 快速运行

运行环境为 Python 3.11 或 3.12（当前音频分析依赖标准库 `audioop`）。

```bash
python3.11 -m voiceproof check-text --script examples/script.txt --transcript examples/transcript.txt --term OpenAI --output reports/text.json
python3.11 -m voiceproof check-wav --audio your.wav --output reports/audio.json
python3.11 -m unittest discover -s tests -v
```

当前不包含自动语音识别、上传服务、账号、支付或外部发布。音频必须是未压缩 PCM WAV；其他格式将在后续验证供应商和用户需求后接入。

## 输入与结果复核

文本文件使用 UTF-8（支持 BOM），原稿和转写均需包含可识别文字或数字。可重复传入 `--term` 检查术语，包括带空格的英文词组。文本报告中的范围是分词索引；标点、大小写和空白在对齐时忽略。新增内容当前统一标记为 `repetition`，需人工判断是否确属重复；数字检查暂不理解中文数字或数字语义。

WAV 支持 8/16/24/32 位整数 PCM、单声道和多声道。静音按约 100 ms 窗口检测（默认连续至少 1200 ms），阈值按位深换算；多声道共用 RMS，某个声道单独静音可能不被标记。削波及低音量是峰值线索。空音频、截断文件和不支持的格式会返回错误。

成功生成 JSON 报告时退出码为 0，即使报告包含疑似问题；输入或写入失败返回 1，参数错误返回 2。错误写入标准错误。输出路径不能指向输入文件。失败时不会生成新报告；若输出位置已有旧报告，请按退出码判断本次运行是否成功。
