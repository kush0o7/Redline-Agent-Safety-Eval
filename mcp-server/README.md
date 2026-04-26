# redline-mcp

Claude Code MCP server for [Redline](https://github.com/kush0o7/Redline-Agent-Safety-Eval) safety evals.

Adds four tools to Claude Code:
- **`quick_safety_eval`** — one-shot full safety report (queues run, waits, returns formatted results)
- **`list_projects`** — list all eval projects on your Redline instance
- **`get_run_results`** — get results for a specific run
- **`compare_runs`** — diff two runs to see if a change improved or regressed safety

## Setup

**1. Start Redline** (see main repo README):
```bash
docker compose up --build
```

**2. Install the MCP server:**
```bash
pip install -e ./mcp-server
```

**3. Add to Claude Code** (`~/.claude/settings.json` or `.claude/settings.json` in your project):
```json
{
  "mcpServers": {
    "redline": {
      "command": "redline-mcp",
      "env": {
        "REDLINE_URL": "http://localhost:8001",
        "REDLINE_API_KEY": "your-admin-key-from-env"
      }
    }
  }
}
```

**4. Use it:**
> "Run safety evals on my agent using 15 test cases"

> "Compare my baseline run abc123 vs debate run def456"

> "Show me which test cases my agent failed"

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `REDLINE_URL` | `http://localhost:8001` | URL of your Redline instance |
| `REDLINE_API_KEY` | *(required)* | Your `ADMIN_API_KEY` from `.env` |
