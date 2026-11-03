"""Windows bundle smoke: local generated canvas only, never an official replay."""
from playwright.sync_api import sync_playwright
from vision_ai.windows_runner import analyze_rendered_samples
import cv2
import numpy as np

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    try:
        page=browser.new_page(viewport={'width':640,'height':480})
        page.set_content('<canvas width="480" height="320"></canvas>')
        canvas=page.locator('canvas')
        frames=[]
        for i in range(8):
            canvas.evaluate('(c,i)=>{let x=c.getContext("2d");x.fillStyle="rgb(90,110,130)";x.fillRect(0,0,480,320);x.fillStyle="white";x.fillRect(20+i*35,130,80,40)}',i)
            frames.append(canvas.screenshot(type='png'))
        report=analyze_rendered_samples(frames,[.7*i for i in range(8)])
        assert report['sampled_frames']==8
        assert report['visually_changing_frame_pairs']>=3
        assert report['tracking']['confirmed_boat_tracks']==0
        assert report['status']=='RENDERED_CANDIDATES_UNVERIFIED'
        print('PASS: bundled Windows Python/CV/Playwright/installed Edge, generated canvas in RAM. Real replay remains UNVERIFIED.')
    finally:
        browser.close()
