# Mempalace — regras de uso

Carrega esta regra quando o contexto envolver mempalace, diary, AAAK, ou memória persistente.

## Ambiente canónico

- Repo: `__HOME__/mempalace` (fork jorgeccastro/mempalace, editable install)
- Venv/runtime: `__HOME__/.mempalace-env/bin/python`
- MCP server: `python -m mempalace.mcp_server` (lançado pelo Claude Code via config em `.claude.json`)
- Versões: verificar com comandos, não confiar neste ficheiro (mudam com upgrades)

## Formato AAAK

Escrita no mempalace (diary_write, add_drawer): usar sempre formato AAAK compacto.

- Campos separados por `|`, compressão com `.`, entity codes, emotion markers
- Chaves comuns: SESSION, TOPIC, ACT, DONE, STATUS, STATE, NEXT, BLOCKED, NOTES, CAUSE, FIX, ERR, LESSON, HW, SW, CMD, MODIFIED, DEPS, RES
- Importancia: `★` a `★★★★★`
- Ex: `SESSION:2026-04-08|TASK:foo.bar|STATUS:done|NOTES:x.y.z|★★★`

## Canais de memória

- **Diary** (diary_write/read): journal de sessão — o que aconteceu, decisões, estado, handoff
- **Knowledge Graph** (kg_add/query): factos duradouros — preferências, ambientes, relações, lições
- **Drawers** (add_drawer): conteúdo estruturado por wing/room/hall

## Disciplina de pesquisa low-token

- Não fazer despejo de contexto. Preferir 2-3 pesquisas curtas a 1 pesquisa com muitos resultados.
- Ordem default:
  1. Uma query natural curta
  2. Se a primeira vier fraca, uma query keyword-only
  3. Só depois uma query com sinónimos/aliases PT-EN ou entidade canónica
- Usar `limit` pequeno por defeito (`3` ou `5`). Não puxar `10+` resultados sem motivo forte.
- Só chamar `mempalace_list_wings`, `mempalace_list_rooms` ou `mempalace_get_taxonomy` quando a taxonomy for realmente necessária para resolver wing/room. Não usar como reflexo.
- Para factos duradouros: consultar primeiro `kg_query`.
- Para trabalho recente, decisões de sessão, handoff ou "o que aconteceu": consultar primeiro `diary_read` ou procurar em `room=diary`.
- Fazer broad search primeiro e só depois afunilar por `wing`/`room` quando houver pista concreta.
- Se o top result não responder claramente, reformular e pesquisar outra vez; não inventar.
- Se a pergunta tiver nomes próprios, produtos, siglas ou marcas, tentar pelo menos uma variante com aliases (`SharePoint`/`OneDrive`, `guest`/`convidado`, etc.).
- Em respostas longas, resumir os hits relevantes em vez de colar vários textos verbatim.

## Política de memória

Guardar:
- Preferências persistentes do utilizador
- Caminhos de ambiente e configuração
- Decisões de arquitetura
- Workflows aprovados
- Erros recorrentes e lições aprendidas

Não guardar:
- Estado efémero ou outputs temporários
- Tentativas falhadas sem valor futuro
- Detalhes redundantes com o que já está em ficheiros

## Curadoria

- Uma tarefa = uma entrada final. Checkpoints intermédios (drafted, pending, awaiting) só se bloquearem trabalho
- Não duplicar a mesma decisão em várias entradas — apontar para a entrada canónica
- Separar claramente: policy (regra duradoura) vs lesson (erro/aprendizagem) vs status (progresso de tarefa)
- Meta-trabalho (config do próprio Claude) merece no máximo uma entrada consolidada, não uma sequência
- Antes de guardar, perguntar: "isto muda comportamento futuro, evita erro futuro, ou preserva contexto que não está noutro lado?" — se não, não guardar
- Antes de apagar, consolidar: fundir detalhes úteis na entrada canónica primeiro, só depois apagar as redundantes
