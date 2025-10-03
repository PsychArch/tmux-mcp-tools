# tmux-mcp-tools

MCP server providing tools for interacting with tmux sessions.

## Features

### Tmux Tools
- `tmux_capture_pane`: Capture the content of a tmux pane
- `tmux_send_command`: Send commands to a tmux pane with automatic Enter key
- `tmux_send_keys`: Send keys to a tmux pane without automatic Enter
- `tmux_write_file`: Write content to a file using heredoc pattern in a tmux pane

## Usage

Add to your MCP client configuration (e.g., Claude Desktop, Cursor):

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

