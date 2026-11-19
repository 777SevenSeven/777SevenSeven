import argparse
import asyncio
import os
import sys
from playwright.async_api import async_playwright

async def capture_badge(user_public_id: str, output_path: str):
    user_public_id = str(user_public_id).strip()
    if not user_public_id:
        print("ERROR: user_public_id is required")
        sys.exit(1)
        
    url = f"https://tryhackme.com/api/v2/badges/public-profile?userPublicId={user_public_id}"
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        page = await browser.new_page(
            viewport={"width": 450, "height": 250},
            device_scale_factor=2
        )
        print(f"Fetching badge from: {url}")
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)
        
        # Look for the badge container element
        element = await page.query_selector("#root, main, div[class*='badge'], body > div")
        if element:
            box = await element.bounding_box()
            if box and box["width"] > 50 and box["height"] > 30:
                padding = 4
                await page.screenshot(
                    path=output_path,
                    clip={
                        "x": max(0, box["x"] - padding),
                        "y": max(0, box["y"] - padding),
                        "width": box["width"] + (padding * 2),
                        "height": box["height"] + (padding * 2),
                    },
                    omit_background=True
                )
            else:
                await page.screenshot(path=output_path, omit_background=True)
        else:
            await page.screenshot(path=output_path, omit_background=True)
            
        await browser.close()
    
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        print(f"Successfully generated badge: {output_path} ({os.path.getsize(output_path)} bytes)")
    else:
        print("ERROR: Badge generation failed.")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-public-id", default=os.getenv("THM_USER_PUBLIC_ID", ""))
    parser.add_argument("--output", default="assets/thm_propic.png")
    args = parser.parse_args()
    
    user_id = args.user_public_id.strip()
    if not user_id:
        print("ERROR: Missing TryHackMe userPublicId. Set THM_USER_PUBLIC_ID secret or pass --user-public-id.")
        sys.exit(1)
        
    asyncio.run(capture_badge(user_id, args.output))
