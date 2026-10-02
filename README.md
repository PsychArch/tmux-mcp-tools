# tmux-mcp-tools

## Retired

This project was retired on 2026-10-02 and is no longer maintained. Use tmux
directly through your agent's shell tool. The source is retained for reference,
and automated PyPI publishing has been removed.

For long-running or interactive work, create a dedicated tmux window, keep its
pane ID, and use `send-keys` and `capture-pane` to interact with it:

```sh
tmux new-window -d -n agent-task -P -F '#{pane_id}'
# Replace %12 with the pane ID returned above.
tmux send-keys -t %12 -l 'python -m http.server 8000'
tmux send-keys -t %12 Enter
tmux capture-pane -p -t %12 -S -100
tmux send-keys -t %12 C-c
```

The documentation below describes the historical MCP interface.

MCP server providing tools for interacting with tmux sessions.

## Tools

- **tmux_create_pane**: Must create a dedicated pane before running background servers, REPLs, remote shells, or other long-running tasks
- **tmux_capture_pane**: Read pane contents with optional delay and scroll-back
- **tmux_send_keys**: Send raw keystrokes (no auto-Enter) for interactive programs
- **tmux_send_command**: Execute commands with auto-Enter, optional wait pattern
- **tmux_write_file**: Write files via heredoc (for remote/SSH environments)

## Configuration

```json
{
  "mcpServers": {
    "tmux-mcp-tools": {
      "command": "uvx",
      "args": ["tmux-mcp-tools"]
    }
  }
}
```

### Options

- `--transport`: `stdio` (default) or `http`
- `--host`: HTTP host (default: 127.0.0.1)
- `--port`: HTTP port (default: 8080)
- `--enter-delay`: Delay before sending Enter in seconds (default: 0.4)
