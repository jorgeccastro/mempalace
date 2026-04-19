# Mempalace — Setup

> 🇬🇧 English: [`README.md`](README.md)

Scripts de bootstrap + dotfiles para reproduzir a integração completa
mempalace + Claude Code noutra máquina.

## Dois modos de instalação

Escolhe um — são complementares, não exclusivos.

| Modo | Palace vive em | Bom para |
|---|---|---|
| **A. Standalone local** (`./install.sh`) | Cada máquina | Utilizadores single-PC, trabalho offline, CLI completa (`mine`, `codex_checkpoint_watcher`) |
| **B. Palace partilhado no VPS** (`./install-vps-server.sh` + `./install-vps-client.sh`) | Um VPS, partilhado entre N clientes via SSH | Múltiplas máquinas, continuidade de memória cross-device, memória partilhada estilo equipa |

Podes correr **os dois**: CLI local + MCP remoto. A CLI usa um palace local; o Claude Code usa o palace do VPS. Não interferem.

---

## A. Instalação standalone local

### O que instala

- `$HOME/.mempalace-env/` — venv Python com mempalace em editable install (este fork)
- `$HOME/.mempalace/hooks/` — hooks Stop + PreCompact (save periódico a cada 10 mensagens do user, save de emergência antes de compactação)
- `$HOME/.claude/CLAUDE.md` — regras globais do Claude (defaults PT-PT, política mempalace-first para memória, verify-don't-invent)
- `$HOME/.claude/rules/mempalace.md` — regras de uso do mempalace carregadas sob demanda (formato AAAK, disciplina de search low-token, política de curadoria)
- `$HOME/.claude/rules/verification.md` — regras de verificação de estado
- Merge em `$HOME/.claude/settings.json` — regista hooks, desactiva `autoMemoryEnabled`
- Merge em `$HOME/.claude.json` — adiciona mempalace como MCP server sob o projecto `$HOME`

### Instalar

```bash
git clone <url-do-teu-fork> mempalace
cd mempalace
./setup/install.sh
```

Depois reinicia o Claude Code.

### Pré-requisitos

- `git`, `python3` (3.12+), `jq`, `pip`
- Claude Code CLI já instalado
- macOS ou Linux (não testado em Windows)

### Idempotência

Seguro para voltar a correr. Ficheiros existentes são guardados com sufixo `.bak.YYYYMMDD-HHMMSS` antes de serem sobrescritos. Ficheiros JSON são deep-merged via `jq` em vez de substituídos.

---

## B. Palace partilhado no VPS

Corre um único palace mempalace num VPS, liga múltiplos clientes a ele via SSH stdio. Vê **[`VPS_SETUP.pt.md`](VPS_SETUP.pt.md)** para arquitectura, pré-requisitos e walkthrough completo.

Fluxo rápido:

```bash
# ── No VPS (como utilizador dedicado sem privilégios) ──────────────────
git clone <url-do-teu-fork> ~/mempalace-source
cd ~/mempalace-source
./setup/install-vps-server.sh
# depois adiciona pubkeys SSH dos clientes a ~/.ssh/authorized_keys

# ── Em cada cliente ────────────────────────────────────────────────────
git clone <url-do-teu-fork> ~/src/mempalace-source
cd ~/src/mempalace-source
VPS_HOST=o-teu-vps-host ./setup/install-vps-client.sh
```

O installer do cliente pede (ou aceita via env vars) `VPS_HOST`, `VPS_USER` (default `mempalace`) e `VPS_PYTHON` (default `/home/mempalace/.mempalace-env/bin/python`), depois ou faz auto-patch ao `~/.claude.json` ou imprime a entry MCP pronta a colar.

Transporte é SSH stdio — zero portas abertas, funciona através de qualquer firewall que permita SSH outbound. Usa Tailscale / WireGuard / Cloudflare Tunnel se quiseres mesh privada; SSH público directo também funciona.

---

## O que NÃO está incluído (em nenhum modo)

- Os teus dados pessoais mempalace (`$HOME/.mempalace/palace/`) — cada instalação começa vazia
- Definições pessoais do Claude (status line, permission prompts, info de conta, skills)
- Tokens, chaves de API, estado OAuth
- Chaves SSH, configs Tailscale, regras de firewall (responsabilidade do operador no modo VPS)

## Customização pós-instalação

Os ficheiros instalados são ponto de partida, não contrato permanente. Edita livremente:

- `~/.claude/CLAUDE.md` — muda idioma, tom, defaults
- `~/.claude/rules/*.md` — ajusta regras mempalace/verification ao teu workflow
- `~/.mempalace/hooks/mempal_save_hook.sh` — afina `SAVE_INTERVAL` (default: save a cada 10 mensagens reais do user)

## Desinstalar

**Standalone:**
```bash
rm -rf $HOME/.mempalace-env $HOME/.mempalace/hooks
rm $HOME/.claude/rules/mempalace.md $HOME/.claude/rules/verification.md
# Restaura CLAUDE.md, settings.json, .claude.json a partir dos .bak se quiseres
```

**Cliente VPS:**
```bash
# Remove a entry mcpServers.mempalace de ~/.claude.json
# Revoga a pubkey do cliente do authorized_keys do utilizador VPS
```

**Servidor VPS:**
```bash
# No VPS, como utilizador mempalace
rm -rf ~/.mempalace-env ~/.mempalace ~/mempalace-source
# Depois remove o user se for dedicado: sudo userdel -r mempalace
```
