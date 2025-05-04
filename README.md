# tmux-mcp-tools

A Model Context Protocol (MCP) server that provides tools for interacting with tmux sessions.

## Installation


## Features

- `tmux_capture_pane`: Capture the content of a tmux pane
- `tmux_send_command`: Send commands to a tmux pane with automatic Enter key
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

