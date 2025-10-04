"""
MCP Server for tmux-mcp-tools

This server implements the Model Context Protocol (MCP) for tmux operations,
providing tools to interact with tmux sessions.
"""

import argparse
import sys

from fastmcp import FastMCP

from . import config
from .tools import register_tools

# Create FastMCP server
mcp = FastMCP(name="TmuxTools")


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
    parser.add_argument(
        "--enter-delay",
        type=float,
        default=0.4,
        help="Delay in seconds before sending Enter (C-m) for commands and file operations. This delay allows users to press C-c to interrupt if needed. (default: 0.4)"
    )

    args = parser.parse_args()

    # Set global settings from command line arguments
    config.ENTER_DELAY = args.enter_delay

    # Register all tools
    register_tools(mcp)

    # Start server with appropriate transport
    try:
        if args.transport == "stdio":
            mcp.run(transport="stdio", show_banner=False)
        else:
            mcp.run(transport="http", host=args.host, port=args.port, show_banner=False)
    except Exception as e:
        print(f"Error starting server: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
