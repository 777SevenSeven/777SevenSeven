import argparse
import asyncio
import os
import sys
from playwright.async_api import async_playwright

DEFAULT_BADGE_URL = "https://tryhackme.com/badge/t/70d485e8289b4abc0225716dce9daf94f6fdc0cb34d993fd14683c20884bff9b6bd52e954811cb97a1900213bbd3cdb9/embed?theme=dark"

async def capture_badge(badge_url: str, output_path: str):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        # 400x172 matches TryHackMe iframe exact dimensions, device_scale_factor=2 produces crisp retina image
        page = await browser.new_page(
            viewport={"width": 400, "height": 172},
            device_scale_factor=2
        )
        print(f"Fetching badge from: {badge_url}")
        await page.goto(badge_url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)
        
        await page.screenshot(path=output_path, omit_background=True)
        await browser.close()
    
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        print(f"Successfully generated badge: {output_path} ({os.path.getsize(output_path)} bytes)")
    else:
        print("ERROR: Badge generation failed.")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.getenv("THM_BADGE_URL", DEFAULT_BADGE_URL))
    parser.add_argument("--output", default="assets/thm_propic.png")
    args = parser.parse_args()
    
    asyncio.run(capture_badge(args.url, args.output))
