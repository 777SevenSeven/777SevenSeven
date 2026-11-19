#!/usr/bin/env python3
"""
Atualiza a badge do TryHackMe com fallback automático.

Estratégia:
  1. Tenta gerar o PNG oficial (screenshot do embed da THM) via Playwright.
     Se o Vercel Security Checkpoint bloquear, o PNG não é gerado.
  2. Independente do resultado, busca as estatísticas reais do perfil na API
     interna /api/v2/public-profile e gera um SVG de fallback.
  3. Aponta o README para o PNG quando ele é gerado com sucesso; caso
     contrário, aponta para o SVG. Na próxima execução bem-sucedida o README
     volta sozinho para o PNG.

Execução local (IP residencial) — runners do GitHub são bloqueados pela Vercel.
"""

import asyncio
import html
import json
import os
import re
import sys
from playwright.async_api import async_playwright

USERNAME = os.getenv("THM_USERNAME", "andreQueiroz")
BADGE_EMBED_URL = os.getenv(
    "THM_BADGE_URL",
    "https://tryhackme.com/badge/t/70d485e8289b4abc0225716dce9daf94f6fdc0cb34d993fd14683c20884bff9b6bd52e954811cb97a1900213bbd3cdb9/embed?theme=dark",
)
API_URL = f"https://tryhackme.com/api/v2/public-profile?username={USERNAME}"
PNG_PATH = "assets/thm_propic.png"
SVG_PATH = "assets/thm_badge.svg"
README_PATH = os.getenv("README_PATH", "README.md")

W, H = 480, 150
BG = "#0d1117"
CARD = "#161b22"
BORDER = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
GREEN = "#64ffda"
CYAN = "#58a6ff"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


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


async def capture_png(page, png_path):
    """Retorna True se o screenshot do embed foi gerado (sem checkpoint)."""
    os.makedirs(os.path.dirname(os.path.abspath(png_path)), exist_ok=True)
    await page.screenshot(path=png_path, omit_background=True)
    return os.path.exists(png_path) and os.path.getsize(png_path) > 1000


async def fetch_profile_data(page):
    """Chama a API de dentro da página do perfil (mesma stack/TLS do browser,
    que passa no desafio da Vercel; cookies de sessão incluídos)."""
    result = await page.evaluate(
        """async (url) => {
            const r = await fetch(url, {headers: {'Accept': 'application/json'}});
            return {status: r.status, body: await r.text()};
        }""",
        API_URL,
    )
    if result["status"] != 200:
        return None
    try:
        return json.loads(result["body"]).get("data")
    except Exception:
        return None


def is_checkpoint(page_content, page_title, status):
    blob = (page_content + " " + page_title).lower()
    return "vercel security checkpoint" in blob or status == 429


def point_readme_to(asset_file, width):
    """Aponta a <img> da badge no README para o asset escolhido."""
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    pattern = re.compile(
        r'(<img src="https://raw\.githubusercontent\.com/777SevenSeven/777SevenSeven/main/assets/)'
        r'thm_(?:propic\.png|badge\.svg)(" alt="TryHackMe[^"]*" width=")[^"]+(")'
    )
    new_content, n = pattern.subn(
        lambda m: f"{m.group(1)}thm_{asset_file}"
                  f"{m.group(2)}{width}{m.group(3)}",
        content,
    )
    if n == 0:
        print("WARN: não encontrei a tag <img> da badge no README — modo não atualizado.")
        return
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)


async def main():
    png_ok = False
    svg_ok = False

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page(
            viewport={"width": 400, "height": 172},
            device_scale_factor=2,
            user_agent=UA,
        )
        response = await page.goto(BADGE_EMBED_URL, wait_until="domcontentloaded", timeout=60000)
        status = response.status if response else None

        # Aguarda o desafio da Vercel auto-resolver (IP residencial passa)
        for _ in range(15):
            await asyncio.sleep(2)
            title = await page.title()
            content = await page.content()
            if not is_checkpoint(content, title, status):
                break

        if not is_checkpoint(await page.content(), await page.title(), status):
            try:
                png_ok = await capture_png(page, PNG_PATH)
                if png_ok:
                    print(f"PNG oficial gerado: {PNG_PATH}")
            except Exception as e:
                print(f"WARN: screenshot falhou ({e})")
        else:
            print("Checkpoint detectado — PNG oficial indisponível, usando fallback SVG.")

        # SVG de fallback: a página do embed tem CSP que bloqueia fetch,
        # então navegamos ao perfil (mesma origem) antes de chamar a API.
        try:
            await page.goto(f"https://tryhackme.com/p/{USERNAME}",
                            wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(5)
            data = None
            for _ in range(10):
                try:
                    data = await fetch_profile_data(page)
                except Exception:
                    data = None
                if data:
                    break
                await asyncio.sleep(2)
            if data:
                os.makedirs(os.path.dirname(os.path.abspath(SVG_PATH)), exist_ok=True)
                with open(SVG_PATH, "w", encoding="utf-8") as f:
                    f.write(build_svg(data))
                svg_ok = True
                print(f"SVG de fallback gerado: {SVG_PATH}")
                print(f"  level={data.get('level')} points={data.get('totalPoints')} "
                      f"rooms={data.get('completedRoomsNumber')} badges={data.get('badgesNumber')} "
                      f"streak={data.get('streak')}")
            else:
                print("WARN: API do perfil indisponível — SVG não atualizado.")
        except Exception as e:
            print(f"WARN: falha ao gerar SVG ({e})")

        await browser.close()

    if png_ok:
        point_readme_to("propic.png", 320)
        mode = "png"
    elif svg_ok or os.path.exists(SVG_PATH):
        point_readme_to("badge.svg", 480)
        mode = "svg"
    else:
        print("ERROR: nenhuma badge pôde ser gerada.")
        sys.exit(2)

    print(f"Modo ativo: {mode.upper()} -> README atualizado.")


if __name__ == "__main__":
    asyncio.run(main())
