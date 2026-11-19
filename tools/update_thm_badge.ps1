# Atualiza a badge do TryHackMe localmente e faz push para o GitHub.
# Necessário porque o TryHackMe bloqueia runners do GitHub (Vercel checkpoint)
# — execute a partir de uma conexão residencial.
#
# Agendado via Agendador de Tarefas do Windows (ver instruções no final).

$ErrorActionPreference = "Stop"
$repo = "C:\Users\André Antonio\Downloads\777SevenSeven"
Set-Location $repo

python .github\scripts\update_badge.py --output assets\thm_propic.png
if ($LASTEXITCODE -ne 0) {
    Write-Host "Badge update failed (exit $LASTEXITCODE) — keeping previous image."
    exit $LASTEXITCODE
}

git add assets\thm_propic.png
$staged = git diff --staged --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "No badge changes."
    exit 0
}

git config user.name "André Antonio"
git config user.email "andredev33@gmail.com"
git commit -m "chore(badge): update TryHackMe badge"
git push origin main
Write-Host "Badge updated and pushed."
