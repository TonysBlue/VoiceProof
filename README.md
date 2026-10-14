# VoiceProof 声检

阶段 0 离线原型：把用户提供的原稿和转写文本对齐，标记疑似漏读、重复、替换、数字与术语差异；同时检查 PCM WAV 的静音和音量。结果是供用户复核的证据，不是“零错误”保证。

## 快速运行

```bash
python3.11 -m voiceproof check-text --script examples/script.txt --transcript examples/transcript.txt --term OpenAI --output reports/text.json
python3.11 -m voiceproof check-wav --audio your.wav --output reports/audio.json
python3.11 -m unittest discover -s tests -v
```

当前不包含自动语音识别、上传服务、账号、支付或外部发布。音频必须是未压缩 PCM WAV；其他格式将在后续验证供应商和用户需求后接入。

