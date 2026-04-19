# mempalace — palace partilhado no VPS

> 🇬🇧 English: [`VPS_SETUP.md`](VPS_SETUP.md)

Corre um único palace mempalace num VPS e tem múltiplos clientes
(Claude Code, Codex, etc. em máquinas diferentes) a falar com ele via SSH.

Esta é uma alternativa **opcional** à instalação standalone
(`setup/install.sh`), em que cada cliente tem o seu próprio palace.

## Arquitectura

```
┌───────────────┐    SSH (stdio)    ┌──────────────────┐
│ cliente PC #1 │ ────────────────▶ │ VPS              │
│ Claude Code   │                   │ mempalace.mcp_sv │
└───────────────┘                   │ palace (único)   │
                                    │ KG (único)       │
┌───────────────┐    SSH (stdio)    │                  │
│ cliente PC #2 │ ────────────────▶ │                  │
│ Codex         │                   │                  │
└───────────────┘                   └──────────────────┘
┌───────────────┐    SSH (stdio)
│ cliente PC #3 │ ───────────────────────────▶
│ Claude Code   │
└───────────────┘
```

- **Palace + KG vivem no VPS** — single source of truth para todos os clientes.
- **Transporte é SSH stdio** — zero portas abertas, funciona através de qualquer firewall que permita SSH outbound. Usa Tailscale / WireGuard / Cloudflare Tunnel se quiseres mesh; SSH público directo também funciona.
- **Clientes não correm processo mempalace** — o MCP server executa no VPS quando o Claude Code lança o comando `ssh …`. Mata-se o SSH, mata-se o server.

## Pré-requisitos

- Um VPS (Linux qualquer) com acesso SSH e Python 3.11+.
- Um utilizador dedicado sem privilégios no VPS (ex.: `mempalace`). Não corras mempalace como root.
- Em cada cliente PC: uma chave SSH que estejas disposto a adicionar ao `authorized_keys` do utilizador VPS.
- (Opcional, recomendado) Tailscale ou equivalente, para o VPS ser alcançável sem expor SSH à internet pública.

## 1 — Instalação no servidor (VPS)

SSH para o VPS, cria o utilizador de serviço se não existir, e corre o installer do servidor dentro de um clone do teu fork:

```bash
ssh you@o-teu-vps
sudo useradd -m -s /bin/bash mempalace      # salta se o utilizador já existe
sudo -iu mempalace
git clone <url-do-teu-fork> ~/mempalace-source
cd ~/mempalace-source
./setup/install-vps-server.sh
```

O que faz:
- instala `uv` se não estiver presente
- cria venv `~/.mempalace-env`
- `uv pip install -e .` a partir do clone
- cria directório de dados `~/.mempalace/`
- imprime o comando que os clientes vão usar

O que NÃO faz:
- adicionar chaves SSH (fazes tu, colando pubkeys dos clientes em
  `/home/mempalace/.ssh/authorized_keys`)
- instalar Tailscale / configurar firewall / gerir DNS
- criar serviço systemd — o MCP server é spawned on-demand por sessão SSH,
  o que é mais simples e dispensa supervisão

## 2 — Autorizar chaves SSH dos clientes

Em cada cliente, gera uma chave se ainda não tiveres:

```bash
ssh-keygen -t ed25519 -C "hostname-do-teu-cliente"
cat ~/.ssh/id_ed25519.pub
```

Copia a linha da pubkey e no VPS, como utilizador mempalace:

```bash
echo "ssh-ed25519 AAAA…" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Testa do cliente:

```bash
ssh mempalace@o-teu-vps-host "whoami"   # deve imprimir: mempalace
```

## 3 — Instalação no cliente (por cada PC cliente)

Clona o repo (qualquer directório — só é usado para o script) e corre:

```bash
git clone <url-do-teu-fork> ~/src/mempalace-source
cd ~/src/mempalace-source
VPS_HOST=o-teu-vps-host ./setup/install-vps-client.sh
```

Pede (ou lê via env):
- `VPS_HOST` — nome Tailscale, nome DNS ou IP
- `VPS_USER` — utilizador SSH (default `mempalace`)
- `VPS_PYTHON` — caminho para o python do venv no VPS (default
  `/home/mempalace/.mempalace-env/bin/python`)

Depois ou faz patch ao `~/.claude.json` (`mcpServers.mempalace`) ou imprime a entry resolvida para colares à mão.

Reinicia o Claude Code depois do patch; o MCP server deve aparecer como `mempalace` com `mempalace_search`, `mempalace_kg_*`, `mempalace_diary_*`, etc.

## Opcional — instalar a CLI local também

O MCP server corre inteiramente no VPS, portanto a CLI do lado do cliente só é necessária se quiseres `mempalace mine` local / `codex_checkpoint_watcher`:

```bash
./setup/install.sh       # install local standard, não precisa VPS para a CLI
```

A CLI local pode partilhar o caminho do palace via SSHFS/NFS ou simplesmente apontar a um palace local próprio — é independente do fluxo MCP do VPS.

## Troubleshooting

- **`Permission denied (publickey)`** — a tua pubkey do cliente não está no `authorized_keys` do utilizador VPS. Revê o passo 2.
- **MCP server fica "connecting" para sempre** — testa o comando raw:
  `ssh mempalace@vps /home/mempalace/.mempalace-env/bin/python -m mempalace.mcp_server`.
  Se ficar em silêncio é correcto (está à espera de JSON-RPC no stdin).
  Envia `{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}` para verificar.
- **`ModuleNotFoundError: mempalace`** no VPS — venv quebrado; corre de novo `./setup/install-vps-server.sh`.
- **Índice HNSW desactualizado depois de escritas via CLI** — chama `mempalace_reconnect` do cliente para forçar o MCP server a reabrir as collections.
