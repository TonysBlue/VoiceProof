"""Internal browser acceptance against real local ASR (no fake transcript).
Run after installing .[local], Playwright Chromium and a local small model:
python scripts/verify_browser.py --model .models/small --output evidence/task-8
"""
import argparse
import json
import sys
import threading
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from voiceproof.server import Application, make_server
from playwright.sync_api import sync_playwright, expect
from make_media_fixtures import convert, TEXT, SOURCE


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    app=Application(args.model.resolve());server=make_server(app=app)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{server.server_port}'
    errors=[];external=[];outcome={}
    started=time.monotonic()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1440,'height':1100})
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('request',lambda request:external.append(request.url) if not request.url.startswith(url) else None)
            page.goto(url);expect(page.locator('#engine')).to_have_text('本地语音引擎已就绪')
            page.screenshot(path=str(args.output/'desktop-input.png'),full_page=True)
            # Deliberately changed script, no injected recognition result.
            page.locator('#media').set_input_files(SOURCE)
            page.locator('#script').fill(TEXT+'感谢观看，下期再见。')
            page.locator('#terms').fill('麦克风')
            page.locator('#submit').click()
            page.locator('#report:not([hidden]), #status.error').first.wait_for(state='visible',timeout=900000)
            if page.locator('#report').is_hidden():
                raise AssertionError(page.locator('#status').inner_text())
            result=app.status()['report']
            assert result['issues'],'Controlled omitted ending should produce a review issue'
            assert page.locator('#conclusion').inner_text()=='建议复核'
            page.locator('.issue .time').first.click()
            page.wait_for_timeout(500)
            assert page.locator('#player').evaluate('(player) => player.currentTime > 0')
            page.get_by_role('button',name='回听确认有问题',exact=True).first.click()
            assert page.locator('#conclusion').inner_text()=='必须重录'
            page.screenshot(path=str(args.output/'desktop-review.png'),full_page=True)
            with page.expect_download() as download:
                page.locator('#export').click()
            download.value.save_as(str(args.output/'browser-report.txt'))
            # Every ignore action must recalculate the conclusion.
            while page.locator('.issue:not(.ignored)').count():
                page.locator('.issue:not(.ignored)').first.get_by_role('button',name='忽略此项',exact=True).click()
            assert page.locator('#conclusion').inner_text().startswith('可忽略')
            directory=app.directory
            page.locator('#clear').click();expect(page.locator('#status')).to_contain_text('已删除')
            assert not directory.exists()
            # Compressed video travels through the exact same production GUI and worker.
            video=args.output/'synthetic-input.mp4';convert(video,'aac',True)
            page.locator('#media').set_input_files(video);page.locator('#script').fill(TEXT);page.locator('#submit').click()
            page.locator('#report:not([hidden]), #status.error').first.wait_for(state='visible',timeout=900000)
            assert not page.locator('#report').is_hidden(),page.locator('#status').inner_text()
            video_result=app.status()['report']
            directory=app.directory
            page.locator('#clear').click();expect(page.locator('#status')).to_contain_text('已删除')
            assert not directory.exists()
            # Bad-media failure has a human-readable recovery path.
            page.locator('#media').set_input_files({'name':'broken.mp4','mimeType':'video/mp4','buffer':b'broken'})
            page.locator('#script').fill(TEXT);page.locator('#submit').click()
            page.locator('#status.error').wait_for(state='visible',timeout=30000)
            assert '重新导出' in page.locator('#status').inner_text()
            page.screenshot(path=str(args.output/'failure.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(args.output/'mobile-layout.png'),full_page=True)
            outcome=dict(elapsed_seconds=round(time.monotonic()-started,2),real_asr=True,real_wav=True,real_mp4=True,
                         click_playback=True,confirm_ignore_export=True,clear_deleted=True,bad_media_recovery=True,
                         mobile_no_horizontal_overflow=True,browser_errors=errors,external_browser_requests=external,
                         wav_report=result,video_report=video_result)
            assert not errors,errors
            assert not external,external
            browser.close()
    finally:
        app.clear();server.shutdown();server.server_close()
    (args.output/'browser-results.json').write_text(json.dumps(outcome,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in outcome.items() if not k.endswith('_report')},ensure_ascii=False))

if __name__=='__main__':main()
