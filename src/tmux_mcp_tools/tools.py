"""
MCP tool implementations for tmux operations.
"""

import re
import subprocess
import time
from typing import Annotated, List, Optional

from fastmcp import FastMCP
from pydantic import Field

from .utils import validate_target_pane, ensure_pane_normal_mode, is_special_key, tmux_send_text


def tmux_create_pane(
    split: Annotated[bool, Field(description="Split current pane vertically. Use this if you are a cli agent for quick commands")] = False,
    name: Annotated[Optional[str], Field(description="Optional name for the window")] = None
) -> str:
    """Create a new tmux pane.

    Returns pane identifier in format [session:]window.pane (e.g., "0:1.0" or "1.0").
    """
    try:
        if split:
            cmd = ["tmux", "split-window", "-v", "-d"]
        else:
            cmd = ["tmux", "new-window", "-d"]
            if name:
                cmd.extend(["-n", name])

        cmd.extend(["-P", "-F", "#{session_name}:#{window_index}.#{pane_index}"])

        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return "Pane: " + result.stdout.strip()

    except subprocess.CalledProcessError as e:
        return f"Error creating pane: {e.stderr}"


def tmux_capture_pane(
    target_pane: str,
    delay: Annotated[float, Field(description="Delay in seconds before capturing (0-60)", ge=0, le=60)] = 0.2,
    scroll_back_screens: Annotated[int, Field(description="Number of screens to scroll back (0 = current screen only)", ge=0)] = 0
) -> str:
    """Read pane contents.

    For checking output from already-running processes.
    """
    # Validate pane_identifier
    try:
        target_pane = validate_target_pane(target_pane)
    except ValueError as e:
        return f"Error: {str(e)}"

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


def tmux_send_keys(
    keys: Annotated[List[str], Field(description="""Keys to send.

special keys: C-x (Control), M-x (Alt), S-x (Shift), Escape, Up, Left, Home, F1-F24
literal texts: Any text NOT matching special key patterns above

Example:  ["python", "C-m", "import sys", "C-m"], ["C", "-", "m"] for input C-m as literal
""")],
    target_pane: str
) -> str:
    """Send raw keystrokes without automatic Enter.

    For:
    - Interactive program control (debuggers, REPLs, TUIs)
    - Control sequences (C-c, navigation)
    - Typing without executing
    """
    if not keys:
        return "Error: No keys specified"

    # Validate pane_identifier
    try:
        target_pane = validate_target_pane(target_pane)
    except ValueError as e:
        return f"Error: {str(e)}"

    # Ensure pane is in normal mode before sending keys
    if not ensure_pane_normal_mode(target_pane):
        return f"Error: Could not ensure pane {target_pane} is in normal mode"

    # Process each key/command in the list
    for key in keys:
        # Determine if this is a special key or literal text
        use_literal = not is_special_key(key)
        tmux_send_text(target_pane, key, literal_mode=use_literal)

    return f"Keys sent."


def tmux_send_command(
    commands: Annotated[List[str], Field(description="Commands to send")],
    target_pane: str,
    delay: Annotated[float, Field(description="Timeout in seconds.", ge=0, le=300)] = 5,
    wait_for_pattern: Annotated[Optional[str], Field(description="Regex to wait for in the terminal outputs. Polls until match or timeout.")] = None
) -> str:
    """Execute commands with automatic Enter.

    CRITICAL: Use wait_for_pattern or analyze the last line of output:
    - Shell prompt (pattern like r'user@host.*\\$') → command completed, safe to proceed
    - Program prompt ((gdb) >>> mysql>) → interactive mode, send input as needed
    - No prompt / progress indicators → still executing, wait or check with tmux_capture_pane
    """

    # Validate pane_identifier
    try:
        target_pane = validate_target_pane(target_pane)
    except ValueError as e:
        return f"Error: {str(e)}"

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

    # If wait_for_pattern is specified, poll for the pattern
    if wait_for_pattern:
        pattern_re = re.compile(wait_for_pattern)
        start_time = time.time()

        # Get initial cursor position for tracking new output
        initial_info = subprocess.run(
            ["tmux", "display-message", "-p", "-t", target_pane, "#{cursor_y},#{history_size}"],
            check=True, stdout=subprocess.PIPE, text=True
        )
        last_checked_y, last_history = map(int, initial_info.stdout.strip().split(','))

        while time.time() - start_time < delay:
            time.sleep(0.5)
            
            # Get current cursor position and history
            current_info = subprocess.run(
                ["tmux", "display-message", "-p", "-t", target_pane, "#{cursor_y},#{history_size}"],
                check=True, stdout=subprocess.PIPE, text=True
            )
            current_y, current_history = map(int, current_info.stdout.strip().split(','))

            # Capture new output since last check
            # If history changed, we need to account for scrolled lines
            history_diff = current_history - last_history
            start_line = last_checked_y - history_diff

            result = subprocess.run(
                ["tmux", "capture-pane", "-p", "-t", target_pane,
                 "-S", str(start_line), "-E", str(current_y)],
                check=True, stdout=subprocess.PIPE, text=True
            )

            # Check if pattern is in the new output
            if pattern_re.search(result.stdout):
                break

            last_checked_y = current_y
            last_history = current_history

    else:
        # Wait for commands to execute and output to stabilize (original behavior)
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

    # Include the command line in output for LLM context
    total_output_lines = cursor_y_diff + history_diff

    # If no output detected, return empty string
    if total_output_lines <= 0:
        return ""

    # Step 2: Capture the output
    # End is always the current cursor position to include the prompt
    end_line = after_y

    # Start is computed based on how many lines we need to capture
    # This can be negative (to capture lines that have scrolled off)
    start_line = end_line - total_output_lines

    # Capture the content including the current line (prompt)
    capture_cmd = ["tmux", "capture-pane", "-p", "-t", target_pane,
                  "-S", str(start_line), "-E", str(end_line)]
    result = subprocess.run(capture_cmd, check=True, stdout=subprocess.PIPE, text=True)

    return result.stdout.strip()


def tmux_write_file(
    file_path: Annotated[str, Field(description="Path to the file")],
    content: Annotated[str, Field(description="File content")],
    target_pane: str
) -> str:
    """Write file using heredoc. 

    Mainly for remote environments (SSH, containers) without direct filesystem access.
    """
    if not file_path:
        return "Error: No file path specified"

    # Validate pane_identifier
    try:
        target_pane = validate_target_pane(target_pane)
    except ValueError as e:
        return f"Error: {str(e)}"

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
    verify_cmd = f"[ -f {file_path} ] && echo 'success' || echo 'failed'"
    # Send command without enter and capture cursor position after command
    tmux_send_text(target_pane, verify_cmd, with_enter=False)

    # Get cursor position after command is typed (but not executed)
    after_command = subprocess.run(
        ["tmux", "display-message", "-p", "-t", target_pane, "#{cursor_y}"],
        check=True, stdout=subprocess.PIPE, text=True
    )
    command_end_y = int(after_command.stdout.strip())

    # Now send enter to execute the command
    tmux_send_text(target_pane, "C-m", with_enter=False)

    # Wait for command to execute
    time.sleep(0.2)

    # Get final cursor position after execution
    after_execution = subprocess.run(
        ["tmux", "display-message", "-p", "-t", target_pane, "#{cursor_y}"],
        check=True, stdout=subprocess.PIPE, text=True
    )
    final_cursor_y = int(after_execution.stdout.strip())

    # Calculate capture range: output starts after command line, ends before prompt
    start_line = command_end_y + 1  # First line after command
    end_line = final_cursor_y - 1   # Last line before prompt

    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-t", target_pane, "-S", str(start_line), "-E", str(end_line)],
        check=True, stdout=subprocess.PIPE, text=True
    )

    return result.stdout.strip()


def register_tools(mcp: FastMCP):
    """Register all MCP tools with the server."""

    mcp.tool()(tmux_create_pane)
    mcp.tool()(tmux_capture_pane)
    mcp.tool()(tmux_send_keys)
    mcp.tool()(tmux_send_command)
    mcp.tool()(tmux_write_file)
