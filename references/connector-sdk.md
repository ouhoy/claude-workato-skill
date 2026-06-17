# Building a custom connector — use the Workato Connector SDK (NOT this skill)

This skill operates **recipes** through the Platform/Developer REST API. It cannot build or
edit a **connector** — the integration adapter that defines how Workato talks to one app/API
(its connection, triggers, actions, object_definitions, methods). Those are different layers:
a connector is the *brick*; a recipe is the *model* you assemble from bricks and run.

> The REST API stores recipe `code` verbatim (golden rule #1) — it has **no** surface for
> connector source. Do not try to author connector logic through `wk.py`; it isn't possible.
> Reach for the SDK below instead.

## When you actually need it

Only when the work is connector-level, not recipe-level:

- The app/API you need has **no Workato connector** (nothing in the connector library) — you
  must build one.
- You **own/maintain a custom connector** (e.g. a partner or in-house adapter) and must change
  its connection, an action/trigger, or its schema.

If the connector already exists (Orderful poller, Shopify, Gmail, json_parser, logger, HTTP,
…) you are doing recipe work — **stay in this skill**, not the SDK.

## What it is

`workato-connector-sdk` is a **Ruby gem** for developing a connector locally: real Ruby
syntax, RSpec unit tests, VCR HTTP cassettes, encrypted credentials, and CI via GitHub Actions
— then push to a workspace. Connector code lives in a single `connector.rb` (a Ruby
hash/DSL). It is a separate toolchain with its own dependency (Ruby), which is why it is **not**
bundled into this zero-dep Python skill.

```sh
gem install workato-connector-sdk
```

## The CLI workflow

| Goal | Command |
|---|---|
| Scaffold a new connector project | `workato new <path>` (pick **1 – secure** for encrypted HTTP mocks) |
| Run one action / trigger / method with test data | `workato exec actions.<name>.execute` · `triggers.<name>.poll` · `methods.<name> --args=input.json` |
| Edit encrypted credentials | `workato edit settings.yaml.enc` (creates `settings.yaml.enc` + `master.key`) |
| Simulate an OAuth2 authorization flow | `workato oauth2` |
| Generate a schema from JSON/CSV, or test scaffolding | `workato generate …` |
| Run the test suite | `bundle exec rspec` (or `… ./spec/connector_spec.rb:16` for one example) |
| Deploy the connector to your workspace | `workato push` |

## Traps

- **`master.key` must be git-ignored.** `workato edit` writes it next to `settings.yaml.enc`;
  committing it leaks every encrypted credential. The scaffold's `.gitignore` covers it —
  don't undo that.
- **`workato push` needs API-client permission.** The API client whose token you push with
  must have the connector "Get details" privilege enabled, or the push is rejected.
- **It does not operate recipes.** No list/inspect/start/stop/job-debug — that is this skill's
  job. The SDK's surface is connector authoring only.

## The handoff (how the two fit together)

They compose cleanly, they don't compete:

1. **SDK** — build + test + `workato push` the connector into the workspace.
2. **This skill (`wk.py`)** — build and operate the **recipes** that consume that connector:
   create, wire datapills, `start`-as-validator, inspect a job's `lines[]`, fix, start/stop.

So a brand-new integration is *SDK first* (make the brick), *this skill second* (assemble and
run the model). Most days you only do step 2.

> Official docs: <https://docs.workato.com/developing-connectors/sdk.html> ·
> CLI: <https://docs.workato.com/developing-connectors/sdk/cli.html> ·
> Source: <https://github.com/workato/workato-connector-sdk>
