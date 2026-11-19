#!/usr/bin/env python3
"""
Análise automática de repositórios públicos -> seção "Selected Projects" do README.

O script pontua cada repo público do usuário por sinais de utilidade real
(descrição, README, atividade, stack, tamanho) e classifica o projeto com uma
label automática (Landing Page, Browser Extension, Game, Security, etc.).
O resultado é injetado no README.md entre os markers AUTO:PROJECTS.
"""

import base64
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
USERNAME = os.getenv("GITHUB_USERNAME", "777SevenSeven")
TOKEN = os.getenv("GITHUB_TOKEN", "")
README_PATH = os.getenv("README_PATH", "README.md")
MAX_PROJECTS = int(os.getenv("MAX_PROJECTS", "6"))
README_FETCH_LIMIT = int(os.getenv("README_FETCH_LIMIT", "12"))

# Repositórios que já possuem seção própria no README ou são arquivos de
# soluções de juízes online (não são "produtos" do portfólio).
EXCLUDED_REPOS = {
    USERNAME.lower(),  # este próprio perfil
    "leetcode-solutions",
    "beecrowd-resolutions",
    "chromium",  # código-fonte do DevTools Enabler, já em destaque no topo
}

# Padrões que indicam material de estudo/curso/trabalho acadêmico, e não um
# produto com utilidade própria. Usados apenas para penalizar o score.
ACADEMIC_PATTERNS = [
    r"\bsolu[cç][oõ]es?\b", r"\bresolutions?\b", r"\bproblems?\b",
    r"\baceitas?\b", r"\baccepted\b", r"\bsubmiss", r"\bbootcamp\b",
    r"\bdesafio\b", r"\bchallenge\b", r"\btrabalho final\b",
    r"\bfaculdade\b", r"\bcollege\b", r"\bcourse\b", r"\bcurso\b",
    r"\bhomework\b", r"\blab\b.*\b(universidade|utfpr|college)\b",
    r"\bnotebooklm\b", r"\bdio[- ]", r"\bplataforma digital innovation\b",
]

# Regras de classificação: (label, [keywords]) — avaliadas sobre
# name + description + início do README, em lowercase.
LABEL_RULES = [
    ("Browser Extension", [
        r"manifest\.json", r"manifest v[23]", r"chrome extension",
        r"firefox extension", r"webextension", r"browser extension",
        r"\bbrowser add-?on\b", r"\bextension\b.*\b(chrome|firefox|edge|browser)",
        r"\b(chrome|firefox|edge)\b.*\bextension\b",
    ]),
    ("Landing Page", [
        "landing page", "landingpage", "landing-page", "one page", "single page",
        "página inicial", "pagina inicial", "site institucional",
    ]),
    ("Game / Interactive", [
        "jogo", "game", "rpg", "jogos", "gameplay", "electron",
        "personagem", "character select", "velha", "snake", "tetris",
        "roleta", "roulette",
    ]),
    ("Security / CTF", [
        "malware", "exploit", "credential", "pentest", "penetration",
        "keylogger", "trojan", "vulnerab", "ciberseguran", "cybersecurity",
        "infosec", "security", "ctf", "offensive", "defensive",
        "metasploit", "metasploitable", "forensic", "osint", "recon",
    ]),
    ("Real Estate", [
        "real estate", "realstate", "im[oó]veis", "properties", "imobili",
    ]),
    ("Pet / E-commerce", [
        "petshop", "pet shop", "e-commerce", "ecommerce", "loja online",
        "marketplace", "checkout", "carrinho",
    ]),
    ("AI / Automation", [
        r"\bai\b", "artificial intelligence", r"\bllm\b", "machine learning",
        "agente", "agent", "automation", "automatiza", "chatbot",
        "openai", "claude", "gemini", "tensorflow", "dataset",
    ]),
    ("Dashboard / Data", [
        "dashboard", "analytics", "gr[aá]ficos", "charts", "bi ",
        "data visualization", "financeiro", "finan[cç]as", "budget",
        "relat[oó]rios", "report",
    ]),
    ("IoT / Embedded", [
        "arduino", "stm32", "esp32", "raspberry", "iot", "embedded",
        "firmware", "sensor", "microcontrolador", "robot",
    ]),
    ("API / Backend", [
        "rest api", "graphql", "backend", "microservice", "servidor",
        "express", "fastapi", "flask", "django", "node.js api", "jwt",
    ]),
    ("Mobile", [
        "flutter", "react native", r"\bandroid\b", r"\bios\b", "mobile app",
        "kotlin", "swift",
    ]),
    ("CLI / Tooling", [
        "cli ", "cli-", "command line", "terminal", "devtool", "dev tool",
        "script", "automatiz", "bot ",
    ]),
]

LABEL_COLORS = {
    "Browser Extension": "4285F4",
    "Landing Page": "0e8a16",
    "Game / Interactive": "a855f7",
    "Security / CTF": "d73a4a",
    "Real Estate": "f97316",
    "Pet / E-commerce": "ec4899",
    "AI / Automation": "6366f1",
    "Dashboard / Data": "06b6d4",
    "IoT / Embedded": "f59e0b",
    "API / Backend": "3b82f6",
    "Mobile": "22c55e",
    "CLI / Tooling": "64748b",
    "Web App": "8b949e",
}

FALLBACK_LABEL = "Web App"


def api_get(path, raw=False):
    url = path if path.startswith("http") else f"{API}{path}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "profile-readme-sync")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read()
    return data if raw else json.loads(data)


def fetch_readme(repo):
    try:
        data = api_get(f"/repos/{USERNAME}/{repo}/readme", raw=True)
        return base64.b64decode(data).decode("utf-8", "replace")
    except Exception:
        return ""


def fetch_root_entries(repo):
    try:
        items = api_get(f"/repos/{USERNAME}/{repo}/contents")
        return {i["name"].lower() for i in items if isinstance(i, dict)}
    except Exception:
        return set()


def fetch_languages(repo):
    try:
        return list(api_get(f"/repos/{USERNAME}/{repo}/languages").keys())
    except Exception:
        return []


def classify(name, description, readme, root_entries):
    haystack_parts = [name or "", description or "", (readme or "")[:6000]]
    for marker in ("manifest.json", "package.json", "pubspec.yaml"):
        if marker in root_entries:
            haystack_parts.append(marker)
    haystack = " ".join(haystack_parts).lower()
    for label, keywords in LABEL_RULES:
        for kw in keywords:
            if "\\" in kw:
                if re.search(kw, haystack):
                    return label
            elif kw in haystack:
                return label
    return FALLBACK_LABEL


def score_repo(repo):
    score = 0
    reasons = []
    if repo.get("description"):
        score += 3
        reasons.append("has description")
    if repo.get("homepage"):
        score += 1
        reasons.append("has homepage")
    pushed = repo.get("pushed_at") or ""
    try:
        dt = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - dt).days
        if age_days <= 180:
            score += 2
            reasons.append("active <6m")
        elif age_days <= 730:
            score += 1
            reasons.append("active <2y")
    except Exception:
        pass
    if (repo.get("stargazers_count") or 0) > 0:
        score += 2
        reasons.append("has stars")
    if (repo.get("size") or 0) >= 100:
        score += 2
        reasons.append("substantial size")
    if (repo.get("fork") or repo.get("archived")):
        score -= 10
    text = f"{repo.get('name','')} {repo.get('description') or ''}".lower()
    for pat in ACADEMIC_PATTERNS:
        if re.search(pat, text):
            score -= 6
            reasons.append(f"academic-like ({pat})")
            break
    if repo.get("language"):
        score += 1
    return score, reasons


def clean_description(text, limit=140):
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    # Remove markdown links/images comuns de READMEs
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return text


def description_from_readme(readme):
    if not readme:
        return ""
    # Pula badges/títulos e pega o primeiro parágrafo com conteúdo
    for para in re.split(r"\n\s*\n", readme):
        p = para.strip()
        if not p or p.startswith(("#", "!", "<", "[!", "---", "```")):
            continue
        p = re.sub(r"[#*`\[\]()>]", "", p)
        p = re.sub(r"\s+", " ", p).strip()
        if 30 <= len(p) <= 300:
            return clean_description(p, 140)
    return ""


def shield(label):
    color = LABEL_COLORS.get(label, LABEL_COLORS[FALLBACK_LABEL])
    return (
        f"![{label}](https://img.shields.io/badge/{label.replace(' ', '_')}-{label.replace(' ', '_')}-{color}"
        f"?style=flat-square&logo=github&logoColor=white)"
    )


def render_section(projects):
    lines = [
        "### 🧩 Projetos em destaque",
        "",
        "<sub>Seção gerada automaticamente por GitHub Actions — analisa descrição, README, stack e atividade dos repositórios públicos.</sub>",
        "",
        "| Projeto | O que é | Stack |",
        "| :--- | :--- | :--- |",
    ]
    for p in projects:
        stars = p["stars"]
        star_txt = f" ⭐{stars}" if stars else ""
        lang = p["language"] or "—"
        desc = p["description"] or f"Projeto classificado como {p['label']}."
        lines.append(
            f"| [{p['name']}]({p['url']}){star_txt} | {desc} "
            f"<br>{shield(p['label'])} | `{lang}` |"
        )
    lines += [
        "",
        "<sub>Labels e seleção são automáticas: repos de soluções de juízes, forks e arquivos de estudo são filtrados pelo score de utilidade.</sub>",
    ]
    return "\n".join(lines)


def main():
    repos = api_get(f"/users/{USERNAME}/repos?per_page=100&sort=pushed&type=owner")
    candidates = [
        r for r in repos
        if r["name"].lower() not in EXCLUDED_REPOS
        and not r.get("fork")
        and not r.get("archived")
    ]
    # Fase 1: score só com metadados da listagem
    scored = []
    for r in candidates:
        s, reasons = score_repo(r)
        scored.append((s, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [r for _, r in scored[:README_FETCH_LIMIT]]

    # Fase 2: busca README/conteúdo/linguagens apenas dos melhores
    projects = []
    for r in top:
        readme = fetch_readme(r["name"])
        root = fetch_root_entries(r["name"])
        langs = fetch_languages(r["name"]) or ([r["language"]] if r.get("language") else [])
        label = classify(r["name"], r.get("description"), readme, root)
        desc = r.get("description") or description_from_readme(readme)
        desc = clean_description(desc)
        if not desc:
            desc = f"Repositório de {label.lower()} em {langs[0] if langs else 'tecnologia web'}{', com foco em entrega funcional.'}"
        score, _ = score_repo(r)
        # bônus por ter README e conteúdo analisável
        score += (3 if readme else 0) + (2 if root else 0)
        projects.append({
            "name": r["name"],
            "url": r["html_url"],
            "description": desc,
            "label": label,
            "language": r.get("language"),
            "stars": r.get("stargazers_count") or 0,
            "score": score,
        })
        print(f"  {r['name']}: score={score} label={label}")

    projects.sort(key=lambda p: p["score"], reverse=True)
    projects = projects[:MAX_PROJECTS]

    section = render_section(projects)

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    start_marker = "<!-- AUTO:PROJECTS:START -->"
    end_marker = "<!-- AUTO:PROJECTS:END -->"
    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        re.DOTALL,
    )
    replacement = f"{start_marker}\n\n{section}\n\n{end_marker}"
    if pattern.search(content):
        new_content = pattern.sub(replacement, content)
    else:
        # Fallback: insere antes da seção de estatísticas do GitHub, se existir
        anchor = re.search(r"^## .*[Gg]it[Hh]ub", content, re.MULTILINE)
        if anchor:
            new_content = content[:anchor.start()] + section + "\n\n" + content[anchor.start():]
        else:
            new_content = content.rstrip() + "\n\n" + section + "\n"

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"README.md atualizado com {len(projects)} projetos.")


if __name__ == "__main__":
    main()
