"""
Utility functions for tmux operations.
"""

import subprocess
import time
from . import config


def validate_target_pane(target_pane: str) -> str:
    """
    Validate target_pane format: [session:]window.pane
    Examples: "0:1.0", "1.0", "mysession:2.1"

    Args:
        target_pane: The pane identifier to validate

    Returns:
        Validated pane identifier

    Raises:
        ValueError: If pane format is invalid
    """
    if not target_pane:
        raise ValueError("Pane identifier cannot be empty")

    # Split by colon to separate session from window.pane
    parts = target_pane.split(':')

    if len(parts) == 1:
        # Format: window.pane (session omitted)
        window_pane = parts[0]
    elif len(parts) == 2:
        # Format: session:window.pane
        window_pane = parts[1]
    else:
        # Too many colons
        raise ValueError(f"Invalid pane format: '{target_pane}'. Expected format: [session:]window.pane (e.g., '0:1.0' or '1.0')")

    # Validate window.pane format
    if '.' not in window_pane:
        raise ValueError(f"Invalid pane format: '{target_pane}'. Expected format: [session:]window.pane (e.g., '0:1.0' or '1.0')")

    wp_parts = window_pane.split('.')
    if len(wp_parts) != 2:
        raise ValueError(f"Invalid pane format: '{target_pane}'. Expected format: [session:]window.pane (e.g., '0:1.0' or '1.0')")

    return target_pane


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


def is_special_key(key_str):
    """
    Determine if a string represents a tmux special key or literal text.

    Special keys include:
    - Keys with modifiers: C-, M-, S- (Control, Meta/Alt, Shift)
    - Named keys: Escape, Enter, Tab, Space, etc.

    Args:
        key_str: The key string to check

    Returns:
        bool: True if it's a special key, False if it's literal text
    """
    # Check for modifier keys
    if any(key_str.startswith(prefix) for prefix in ["C-", "M-", "S-"]):
        return True

    # List of common named keys in tmux
    named_keys = {
        "Escape", "Enter", "Tab", "Space", "Backspace", "Delete",
        "Home", "End", "PageUp", "PageDown", "PPage", "NPage",
        "Up", "Down", "Left", "Right",
        "Insert", "IC", "DC",
        "BSpace", "BTab",
    }

    # Check for function keys (F1-F24)
    if key_str.startswith("F") and len(key_str) <= 3:
        try:
            num = int(key_str[1:])
            if 1 <= num <= 24:
                return True
        except ValueError:
            pass

    # If it matches a named key (case-insensitive)
    if key_str in named_keys:
        return True

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
    # Escape trailing semicolons to prevent tmux from treating them as command separators
    # This is necessary regardless of literal_mode because semicolon parsing happens
    # at tmux's command-line parsing level, before the -l flag is processed
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
        time.sleep(config.ENTER_DELAY)  # Use global delay setting
        subprocess.run(
            ["tmux", "send-keys", "-t", target_pane, "C-m"],
            check=True
        )
