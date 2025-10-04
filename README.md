# tmux-mcp-tools

MCP server providing tools for interacting with tmux sessions.

## Tools

- **tmux_create_pane**: Create new pane (window or split)
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
