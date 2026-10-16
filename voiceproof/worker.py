"""Isolated, cancellable worker; never prints raw media, scripts or model errors."""
import json
import sys
from pathlib import Path
from .workflow import run, UserError, MODEL_ID, MODEL_REVISION


def main():
    directory, model_dir = map(Path, sys.argv[1:3])
    def write(name, payload):
        temporary = directory/(name+'.tmp')
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        temporary.replace(directory/name)
    try:
        if len(sys.argv) > 3 and sys.argv[3] == 'setup':
            from huggingface_hub import snapshot_download
            write('progress.json', {'message': '正在下载本地模型（仅下载模型，不上传素材）'})
            snapshot_download(MODEL_ID, revision=MODEL_REVISION, local_dir=str(model_dir))
            write('result.json', {'installed': True})
        else:
            payload = run(directory, model_dir, lambda message: write('progress.json', {'message': message}))
            write('result.json', payload)
    except Exception as error:
        write('result.json', {'error': str(error) if isinstance(error, UserError) else
                             '本地引擎处理失败。请检查模型是否完整、磁盘空间与可用内存，然后重试。'})

if __name__ == '__main__':
    main()
