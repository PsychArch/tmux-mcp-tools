# tmux-mcp-tools

Provide MCP tools for interacting with tmux sessions.

## Configuration

- **Custom XDG**: `$XDG_CONFIG_HOME/tmux-mcp-tools/`
- **`mcp.json`**: MCP server configuration following Cursor format
- **`prompt.md`**: System prompt template for the AI agent

## Tmux Configuration

Add the following to your `.tmux.conf` file to create a keybinding that opens the client in a new pane:

```bash
bind-key M-k split-window -h -p 33 "uvx --from tmux-mcp-tools tmux-agent --target \"$(tmux display-message -t ! -p '#{pane_id}')\" ;"
```

This will bind Alt+K to open a new pane with the client, targeting the current pane.

## Features

### Tmux Tools
- `tmux_capture_pane`: Capture the content of a tmux pane
- `tmux_send_command`: Send commands to a tmux pane with automatic Enter key
- `tmux_send_keys`: Send keys to a tmux pane without automatic Enter
- `tmux_write_file`: Write content to a file using heredoc pattern in a tmux pane

## Usage
```
{
  "mcpServers": {
    "tmux-mcp-tools": {
      "command": "uvx",
      "args": ["tmux-mcp-tools"]
    }
  }
}
```

