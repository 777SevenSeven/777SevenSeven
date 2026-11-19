#!/usr/bin/env python3
"""
Gera assets/thm_badge.svg com estatísticas reais do perfil TryHackMe.

O TryHackMe protege tryhackme.com com Vercel Security Checkpoint, que bloqueia
IPs de datacenter. Por isso o script usa Playwright (browser real) para
carregar o perfil — o desafio é resolvido automaticamente em conexões
residenciais — e depois chama a API interna /api/v2/public-profile de dentro
da página, que retorna JSON com as estatísticas.

Saída: SVG escuro estilo "card" com level, pontos, rooms, badges e streak.
"""

import asyncio
import html
import json
import os
import sys
import urllib.parse
from playwright.async_api import async_playwright

USERNAME = os.getenv("THM_USERNAME", "andreQueiroz")
OUTPUT = os.getenv("THM_BADGE_OUTPUT", "assets/thm_badge.svg")
PROFILE_URL = f"https://tryhackme.com/p/{USERNAME}"
API_URL = f"/api/v2/public-profile?username={USERNAME}"

W, H = 480, 150
BG = "#0d1117"
CARD = "#161b22"
BORDER = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
GREEN = "#64ffda"
CYAN = "#58a6ff"


def esc(s):
    return html.escape(str(s), quote=True)


def stat_block(x, y, label, value, color):
    return (
        f'<text x="{x}" y="{y}" font-family="Segoe UI,Arial,sans-serif" font-size="11" '
        f'fill="{MUTED}" letter-spacing="1">{esc(label.upper())}</text>'
        f'<text x="{x}" y="{y + 22}" font-family="Segoe UI,Arial,sans-serif" font-size="20" '
        f'font-weight="700" fill="{color}">{esc(value)}</text>'
    )


def build_svg(d):
    level = d.get("level", "-")
    points = f"{d.get('totalPoints', 0):,}".replace(",", ".")
    rooms = d.get("completedRoomsNumber", "-")
    badges = d.get("badgesNumber", "-")
    streak = d.get("streak", "-")
    top = d.get("topPercentage")
    top_txt = f"TOP {top}%" if isinstance(top, (int, float)) else ""
    league = (d.get("leagueTier") or "").capitalize()

    blocks = [
        stat_block(24, 58, "Level", level, GREEN),
        stat_block(124, 58, "Points", points, TEXT),
        stat_block(224, 58, "Rooms", rooms, CYAN),
        stat_block(324, 58, "Badges", badges, "#d2a8ff"),
        stat_block(404, 58, "Streak", f"{streak}d", "#ffa657"),
    ]

    sub = " · ".join(p for p in [top_txt, league, "@" + d.get("username", USERNAME)] if p)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="TryHackMe profile {esc(USERNAME)}">
  <rect width="{W}" height="{H}" rx="12" fill="{BG}"/>
  <rect x="1" y="1" width="{W-2}" height="{H-2}" rx="11" fill="{CARD}" stroke="{BORDER}"/>
  <circle cx="34" cy="34" r="14" fill="{GREEN}" opacity="0.15"/>
  <text x="34" y="40" text-anchor="middle" font-family="Segoe UI,Arial,sans-serif" font-size="16" font-weight="800" fill="{GREEN}">THM</text>
  <text x="58" y="32" font-family="Segoe UI,Arial,sans-serif" font-size="15" font-weight="700" fill="{TEXT}">TryHackMe</text>
  <text x="58" y="48" font-family="Segoe UI,Arial,sans-serif" font-size="11" fill="{MUTED}">{esc(sub)}</text>
  <line x1="24" y1="66" x2="{W-24}" y2="66" stroke="{BORDER}"/>
  {''.join(blocks)}
</svg>
"""


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        )
        await page.goto(PROFILE_URL, wait_until="domcontentloaded", timeout=60000)

        # Aguarda o desafio da Vercel ser resolvido (auto-pass em IP residencial)
        data = None
        for _ in range(15):
            await asyncio.sleep(2)
            title = (await page.title()).lower()
            if "vercel security checkpoint" in title or "vercel security checkpoint" in (await page.content()).lower():
                continue
            result = await page.evaluate(
                """async (url) => {
                    const r = await fetch(url, {headers: {'Accept': 'application/json'}});
                    return {status: r.status, body: await r.text()};
                }""",
                API_URL,
            )
            if result["status"] == 200:
                data = json.loads(result["body"]).get("data")
                break
            await asyncio.sleep(2)
        await browser.close()

    if not data:
        print("ERROR: não foi possível obter dados do perfil (checkpoint/bloqueio).")
        sys.exit(2)

    svg = build_svg(data)
    os.makedirs(os.path.dirname(os.path.abspath(OUTPUT)), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Badge SVG gerada: {OUTPUT}")
    print(f"  level={data.get('level')} points={data.get('totalPoints')} "
          f"rooms={data.get('completedRoomsNumber')} badges={data.get('badgesNumber')} "
          f"streak={data.get('streak')}")


if __name__ == "__main__":
    asyncio.run(main())
