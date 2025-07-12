"""
MCP Server for tmux-mcp-tools

This server implements the Model Context Protocol (MCP) for tmux operations,
providing tools to interact with tmux sessions.
"""

import argparse
import logging
import subprocess
import time
import sys
from typing import Annotated, List, Optional, Union

# Configure logging to suppress INFO messages
logging.basicConfig(level=logging.WARNING)

from fastmcp import FastMCP
from pydantic import BaseModel, Field

# Create FastMCP server
mcp = FastMCP(name="TmuxTools", on_duplicate_tools="error", log_level="WARNING")

# Global delay setting (will be set from command line args)
ENTER_DELAY = 0.5  # Default delay before sending C-m (Enter) for commands and file operations


def ensure_pane_normal_mode(target_pane):
    """
    Ensure the target pane is in normal mode (not in copy mode, view mode, etc.).
    
    Args:
        target_pane: The tmux pane identifier
        
    Returns:
        bool: True if pane is now in normal mode, False if there was an error
    """
    try:
        # Check if pane is in any mode
        result = subprocess.run(
            ["tmux", "display-message", "-p", "-F", "#{pane_in_mode}", "-t", target_pane],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        
        # If pane is in a mode (returns '1'), exit the mode
        if result.stdout.strip() == '1':
            # Use send-keys -t <pane> -X cancel to programmatically exit any mode
            # This works regardless of user key bindings
            subprocess.run(
                ["tmux", "send-keys", "-t", target_pane, "-X", "cancel"],
                check=True, stderr=subprocess.PIPE
            )
            
            # Small delay to allow mode exit to complete
            time.sleep(0.1)
        
        return True
        
    except subprocess.CalledProcessError:
        # If any command fails, return False to indicate error
        return False


def tmux_send_text(target_pane, text, with_enter=False, literal_mode=False):
    """
    Helper function to send text to a tmux pane with proper semicolon handling.
    
    Args:
        target_pane: The tmux pane identifier
        text: The text to send
        with_enter: Whether to send an Enter key (C-m) after the text
        literal_mode: Whether to use literal mode (-l flag) for sending text
    """
    # Escape semicolons if they appear at the end of the text
    if text.endswith(";") and not text.endswith("\\;"):
        text = text[:-1] + "\\;"
    
    # Handle special cases
    if text == "C-[":
        # Convert C-[ to Escape for better compatibility
        cmd = ["tmux", "send-keys", "-t", target_pane, "Escape"]
    else:
        # Use the text as provided
        cmd = ["tmux", "send-keys"]
        if literal_mode:
            cmd.append("-l")
        cmd.extend(["-t", target_pane, text])
    
    # Execute the command
    subprocess.run(cmd, check=True)
    
    # Send Enter key if requested
    if with_enter:
        time.sleep(ENTER_DELAY)  # Use global delay setting
        subprocess.run(
            ["tmux", "send-keys", "-t", target_pane, "C-m"],
            check=True
        )
    
@mcp.tool(
    description="Capture the content of a tmux pane and return it as text.",
    tags={"tmux", "capture", "pane"}
)
def tmux_capture_pane(
    target_pane: Annotated[str, Field(description="Target pane identifier (e.g., '0', '1.2', ':1.0', '%1').")] = "0",
    delay: Annotated[float, Field(description="Delay in seconds before capturing (0-10)", ge=0, le=10)] = 0.2,
    scroll_back_screens: Annotated[int, Field(description="Number of screens to scroll back (0 = current screen only)", ge=0)] = 0
) -> str:
    """
    Capture the content of a tmux pane and return it as text.
    
    """
    # Apply delay if specified
    if delay > 0:
        time.sleep(delay)
    
    # Build the capture command
    cmd = ["tmux", "capture-pane", "-p", "-t", target_pane]
    
    # If scroll_back_screens is specified, calculate the start line
    if scroll_back_screens > 0:
        # Get pane height to calculate how many lines to go back
        pane_info = subprocess.run(
            ["tmux", "display-message", "-p", "-F", "#{pane_height}", "-t", target_pane],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        pane_height = int(pane_info.stdout.strip())
        
        # Calculate start line (negative value means going back in history)
        # -1 because we want to include the current screen as screen 0
        start_line = -(scroll_back_screens * pane_height)
        
        # Add start line parameter to capture command
        cmd.extend(["-S", str(start_line)])
    
    # Capture pane content
    result = subprocess.run(
        cmd,
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
    target_pane: Annotated[str, Field(description="Target pane identifier (e.g., '0', '1.2', ':1.0', '%1').")] = "0"
) -> str:
    """
    Send keys or commands to a tmux pane without automatically appending Enter.
    
    """
    if not keys:
        return "Error: No keys specified"
    
    # Ensure pane is in normal mode before sending keys
    if not ensure_pane_normal_mode(target_pane):
        return f"Error: Could not ensure pane {target_pane} is in normal mode"
    
    # Process each key/command in the list
    for key in keys:
        tmux_send_text(target_pane, key)
    
    return f"Keys sent successfully to pane {target_pane}"


@mcp.tool(
    name="tmux_send_command",
    description="Send commands to a tmux pane, automatically appending Enter after each command.",
)
def tmux_send_command(
    commands: Annotated[List[str], Field(description="Commands to send (list of strings)")],
    target_pane: Annotated[str, Field(description="Target pane identifier (e.g., '0', '1.2', ':1.0', '%1').")] = "0",
    delay: Annotated[float, Field(description="Delay in seconds before capturing output (0-10)", ge=0, le=60)] = 2
) -> str:
    """
    Send commands to a tmux pane, automatically appending Enter after each command.
    """
    
    # Ensure pane is in normal mode before sending commands
    if not ensure_pane_normal_mode(target_pane):
        return f"Error: Could not ensure pane {target_pane} is in normal mode"
    
    # Get cursor position and history size before sending command
    before_cmd_format = "#{cursor_x},#{cursor_y},#{history_size},#{pane_height}"
    before_cmd = subprocess.run(
        ["tmux", "display-message", "-p", "-t", target_pane, before_cmd_format],
        check=True, stdout=subprocess.PIPE, text=True
    )
    before_x, before_y, before_history, pane_height = map(
        int, before_cmd.stdout.strip().split(','))
    
    # Process each command in the list
    for command in commands:
        tmux_send_text(target_pane, command, with_enter=True)

    # Wait for commands to execute and output to stabilize
    if delay > 0:
        time.sleep(delay)

    # Get cursor position and history size after command execution
    after_cmd_format = "#{cursor_x},#{cursor_y},#{history_size}"
    after_cmd = subprocess.run(
        ["tmux", "display-message", "-p", "-t", target_pane, after_cmd_format],
        check=True, stdout=subprocess.PIPE, text=True
    )
    after_x, after_y, after_history = map(
        int, after_cmd.stdout.strip().split(','))

    # Step 1: Compute total_output_lines
    cursor_y_diff = after_y - before_y
    history_diff = after_history - before_history
    
    # -1 is to remove the command line itself
    total_output_lines = cursor_y_diff + history_diff - 1
    
    # If no output detected, return empty string
    if total_output_lines <= 0:
        return ""
    
    # Step 2: Capture the output
    # End is always the line before the current cursor position
    end_line = after_y - 1
    
    # Start is computed based on how many lines we need to capture
    # This can be negative (to capture lines that have scrolled off)
    start_line = end_line - total_output_lines + 1
    
    # Capture the content
    capture_cmd = ["tmux", "capture-pane", "-p", "-t", target_pane,
                  "-S", str(start_line), "-E", str(end_line)]
    result = subprocess.run(capture_cmd, check=True, stdout=subprocess.PIPE, text=True)
    
    return result.stdout.strip()

@mcp.tool(
    name="tmux_write_file",
    description="Write content to a file in a tmux pane.",
)
def tmux_write_file(
    file_path: Annotated[str, Field(description="Path to the file to write")],
    content: Annotated[str, Field(description="Content to write to the file")],
    target_pane: Annotated[str, Field(description="Target pane identifier (e.g., '0', '1.2', ':1.0', '%1').")] = "0"
) -> str:
    """
    Write content to a file using the heredoc pattern in a tmux pane.
    
    """
    if not file_path:
        return "Error: No file path specified"
    
    # Ensure pane is in normal mode before writing file
    if not ensure_pane_normal_mode(target_pane):
        return f"Error: Could not ensure pane {target_pane} is in normal mode"
    
    # Start the heredoc command
    tmux_send_text(target_pane, f"cat > {file_path} << 'TMUX_MCP_TOOLS_EOF'", with_enter=True)
    
    # Send the content line by line
    for line in content.split('\n'):
        # Send each line without automatic Enter to avoid delays
        tmux_send_text(target_pane, line, with_enter=False, literal_mode=True)
        # Send a newline manually after each line
        tmux_send_text(target_pane, "C-m", with_enter=False)
    
    
    # End the heredoc
    tmux_send_text(target_pane, "TMUX_MCP_TOOLS_EOF", with_enter=True)
    
    # Verify the file was written by checking if it exists and capturing the result
    verify_cmd = f"[ -f {file_path} ] && echo 'File {file_path} was successfully written' || echo 'Failed to write file {file_path}'"
    tmux_send_text(target_pane, verify_cmd, with_enter=True)
    
    # Wait for command to execute
    time.sleep(0.2)
    
    # Capture the output to get the verification result
    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-t", target_pane],
        check=True, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE, 
        text=True
    )
    
    # Extract the last three lines from the output
    output_lines = [line for line in result.stdout.split('\n') if line.strip()]
    lines_to_return = output_lines[-3:] if len(output_lines) >= 3 else output_lines
    return '\n'.join(lines_to_return)


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
        help="Delay in seconds before sending Enter (C-m) for commands and file operations (default: 0.4)"
    )
    
    args = parser.parse_args()
    
    # Set global delay setting from command line argument
    global ENTER_DELAY
    ENTER_DELAY = args.enter_delay
    
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
