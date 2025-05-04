"""
MCP Server for tmux-mcp-tools

This server implements the Model Context Protocol (MCP) for tmux operations,
providing tools to interact with tmux sessions.
"""

import argparse
import subprocess
import time
import sys
from typing import Annotated, List, Optional, Union

from fastmcp import FastMCP
from pydantic import BaseModel, Field

# Create FastMCP server
mcp = FastMCP(name="TmuxTools", on_duplicate_tools="error")


@mcp.tool(
    description="Capture the content of a tmux pane and return it as text.",
    tags={"tmux", "capture", "pane"}
)
def tmux_capture_pane(
    target_pane: Annotated[str, Field(description="Target pane identifier (e.g., '0', '1.2', ':1.0')")] = "1",
    delay: Annotated[float, Field(description="Delay in seconds before capturing (0-10)", ge=0, le=10)] = 0.2
) -> str:
    """
    Capture the content of a tmux pane and return it as text.
    
    """
    # Apply delay if specified
    if delay > 0:
        time.sleep(delay)
    
    # Capture pane content directly to stdout
    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-t", target_pane],
        check=True, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE, 
        text=True
    )
    
    return result.stdout


@mcp.tool(
    description="Send keys to a tmux pane without automatically appending Enter.",
)
def tmux_send_keys(
    keys: Annotated[List[str], Field(description="List of keys for `tmux send-send`. Escape for ESC, C-m for Enter.")],
    target_pane: Annotated[str, Field(description="Target pane identifier (e.g., '0', '1.2', ':1.0')")] = "1"
) -> str:
    """
    Send keys or commands to a tmux pane without automatically appending Enter.
    
    """
    if not keys:
        return "Error: No keys specified"
    
    # Process each key/command in the list
    for key in keys:
        # Handle special cases
        if key == "C-[":
            # Convert C-[ to Escape for better compatibility
            cmd = ["tmux", "send-keys", "-t", target_pane, "Escape"]
        elif key.endswith(";") and not key.endswith("\\;"):
            # Handle semicolons at the end of a string by escaping them
            # This prevents tmux from interpreting them as command separators
            escaped_key = key[:-1] + "\\;"
            cmd = ["tmux", "send-keys", "-t", target_pane, escaped_key]
        else:
            # Use the key as provided
            cmd = ["tmux", "send-keys", "-t", target_pane, key]
        
        # Execute the command
        subprocess.run(cmd, check=True)
        
        # Small delay to avoid overwhelming the terminal
        time.sleep(0.05)
    
    return f"Keys sent successfully to pane {target_pane}"


@mcp.tool(
    name="tmux_send_command",
    description="Send commands to a tmux pane, automatically appending Enter after each command.",
)
def tmux_send_command(
    commands: Annotated[List[str], Field(description="Commands to send (list of strings)")],
    target_pane: Annotated[str, Field(description="Target pane identifier (e.g., '0', '1.2', ':1.0')")] = "1",
    delay: Annotated[float, Field(description="Delay in seconds before capturing output (0-10)", ge=0, le=10)] = 0.5
) -> str:
    """
    Send commands to a tmux pane, automatically appending Enter after each command.
    """
    if not commands:
        return "Error: No commands specified"
    
    # Process each command in the list
    for command in commands:
        # Send the command
        subprocess.run(
            ["tmux", "send-keys", "-t", target_pane, "-l", command],
            check=True
        )
        
        time.sleep(0.4)
        # Send Enter key (C-m)
        subprocess.run(
            ["tmux", "send-keys", "-t", target_pane, "C-m"],
            check=True
        )
        
        # Small delay to avoid overwhelming the terminal
        time.sleep(0.05)
    
    # Apply delay before capturing output
    if delay > 0:
        time.sleep(delay)
    
    # Capture pane content after commands execution
    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-t", target_pane],
        check=True, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE, 
        text=True
    )
    
    return result.stdout


@mcp.tool(
    name="tmux_write_file",
    description="Write content to a file in a tmux pane.",
)
def tmux_write_file(
    file_path: Annotated[str, Field(description="Path to the file to write")],
    content: Annotated[str, Field(description="Content to write to the file")],
    target_pane: Annotated[str, Field(description="Target pane identifier (e.g., '0', '1.2', ':1.0')")] = "1"
) -> str:
    """
    Write content to a file using the heredoc pattern in a tmux pane.
    
    """
    if not file_path:
        return "Error: No file path specified"
    
    # Start the heredoc command
    subprocess.run(
        ["tmux", "send-keys", "-t", target_pane, f"cat > {file_path} << 'EOF'"],
        check=True
    )
    subprocess.run(
        ["tmux", "send-keys", "-t", target_pane, "C-m"],
        check=True
    )
    
    # Send the content line by line
    for line in content.split('\n'):
        subprocess.run(
            ["tmux", "send-keys", "-t", target_pane, line],
            check=True
        )
        subprocess.run(
            ["tmux", "send-keys", "-t", target_pane, "C-m"],
            check=True
        )
    
    
    # End the heredoc
    subprocess.run(
        ["tmux", "send-keys", "-t", target_pane, "EOF"],
        check=True
    )
    time.sleep(0.4)
    subprocess.run(
        ["tmux", "send-keys", "-t", target_pane, "C-m"],
        check=True
    )
    
    return f"Successfully wrote to file {file_path}"


def get_mcp_server():
    """Return the MCP server instance for use as an entry point."""
    return mcp


def main():
    """Main entry point for the server."""
    parser = argparse.ArgumentParser(description="MCP Server for tmux-mcp-tools")
    parser.add_argument(
        "--transport", 
        choices=["stdio", "http"],
        default="stdio",
        help="Transport protocol to use (default: stdio)"
    )
    parser.add_argument(
        "--host", 
        default="127.0.0.1",
        help="Host to bind to for HTTP transport (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", 
        type=int,
        default=8080,
        help="Port to bind to for HTTP transport (default: 8080)"
    )
    
    args = parser.parse_args()
    
    # Start server with appropriate transport
    try:
        if args.transport == "stdio":
            mcp.run(transport="stdio")
        else:
            mcp.run(transport="http", host=args.host, port=args.port)
    except Exception as e:
        print(f"Error starting server: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
