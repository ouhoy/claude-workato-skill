# Workato Platform-API Skill (for Claude Code / Claude Agent SDK)

A [Claude Code](https://claude.com/claude-code) **skill** that lets Claude drive a Workato
account through its **Platform / Developer REST API** — list, inspect, build, create, fix,
debug, start and stop recipes, and read connections, folders, projects and job runs.

It bundles a zero-dependency Python CLI (`scripts/wk.py`) plus hard-won reference docs (the
recipe `code` JSON DSL, connector encodings, and the API gotchas that otherwise cost hours).

> This is the REST-API skill (drive a Workato workspace with a token). It is **not**
> Workato's hosted "Remote MCP servers" feature.

## What's inside

| Path | What it is |
|---|---|
| `SKILL.md` | The skill itself (Claude loads this) |
| `scripts/wk.py` | Zero-dep (stdlib-only) CLI wrapping the Workato API |
| `references/recipe-code-dsl.md` | Hand-authoring recipe `code`: steps, datapills, `=` formulas, the null-safe `.where(...)[0]['x']` guard, batch-insert shape |
| `references/recipe-gotchas.md` | The traps: verbatim-storage, `start`-as-validator, try/catch hiding failures, safely editing a live recipe, multi-tenant promotion |
| `references/connectors-*.md` | Verified encodings for Gmail, Orderful↔Shopify, json_parser / lookup / logger |
| `references/api-endpoints.md` | Endpoints, regions, rate limits, token scope |
| `evals/` | Eval prompts + a fixture for testing the skill |

## Install

1. Clone, then symlink (or copy) into your Claude skills dir:
   ```sh
   git clone https://github.com/ouhoy/claude-workato-skill.git
   ln -s "$(pwd)/claude-workato-skill" ~/.claude/skills/workato
   ```
2. Provide a Workato API token (US-region tokens start with `wrkaus-`). `wk.py` resolves it
   in this order:
   - env `WORKATO_API_TOKEN`, then
   - file `WORKATO_TOKEN_FILE` (default `~/.config/workato/api_token`).
   ```sh
   mkdir -p ~/.config/workato
   printf '%s' '<your-token>' > ~/.config/workato/api_token
   chmod 600 ~/.config/workato/api_token
   ```
3. (Optional) set `WORKATO_API_BASE` for non-US regions (default `https://www.workato.com/api`;
   `wk.py --region eu|jp|sg|au|il` also works).

## Quick start

```sh
python3 scripts/wk.py scope             # what your token can actually hit
python3 scripts/wk.py recipes           # list recipes (--running, --folder ID)
python3 scripts/wk.py recipe <id> --code
python3 scripts/wk.py jobs <id>
python3 scripts/wk.py -h                # full command list
```

## Token scope

A token is scoped to one API client's role, so many resources may return `401/403` —
run `wk.py scope` first. The reference set this was built against has recipes (R/W) + jobs
+ versions + connections + folders + projects; lookup tables, roles, members, API-platform
and audit logs are typically denied.

## Contributing

PRs welcome. Keep every example free of real credentials, customer/partner names, and
personal data — use placeholders (`you@example.com`, `acme.com`, `<connection-id>`,
`<token>`).

## License

[MIT](LICENSE).
