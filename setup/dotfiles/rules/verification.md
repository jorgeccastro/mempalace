# Verificação de estado — regras

Carrega esta regra quando o contexto envolver diagnóstico, troubleshooting, ou verificação de serviços/instalações.

## Fontes de verdade

- **Estado operacional** (a correr? versão? instalado?): verificar com comandos no runtime correcto
- **Estado do projecto** (código, config, ficheiros): ler os ficheiros locais
- **Factos externos** (docs, versões upstream, preços): pesquisar web/docs oficiais
- **Contexto e continuidade**: mempalace (mas nunca como prova de estado actual)

## Ambientes conhecidos

- mempalace: `__HOME__/.mempalace-env/bin/python`
- Sistema: `python3` (pode diferir do venv)
- Verificar sempre qual o ambiente relevante antes de correr comandos

## Regras

- Não concluir estado a partir de memória ou ficheiros — confirmar com comandos
- Se o ambiente não for óbvio, perguntar ou verificar a config (ex: `.claude.json` para MCP servers)
- Indicar nível de confiança quando não for possível verificar directamente
