#!/usr/bin/env python3
"""Configuration management following XDG Base Directory Specification."""

import os
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigManager:
    """Manages configuration files following XDG Base Directory Specification."""
    
    def __init__(self, app_name: str = "tmux-mcp-tools"):
        self.app_name = app_name
        self._config_dir = self._get_config_dir()
        self._ensure_config_dir()
    
    def _get_config_dir(self) -> Path:
        """Get the XDG config directory for the application."""
        xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config_home:
            return Path(xdg_config_home) / self.app_name
        else:
            return Path.home() / ".config" / self.app_name
    
    def _ensure_config_dir(self) -> None:
        """Ensure the configuration directory exists."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def config_dir(self) -> Path:
        """Get the configuration directory path."""
        return self._config_dir
    
    @property
    def mcp_config_path(self) -> Path:
        """Get the path to the MCP configuration file."""
        return self._config_dir / "mcp.json"
    
    @property
    def prompt_config_path(self) -> Path:
        """Get the path to the prompt configuration file."""
        return self._config_dir / "prompt.md"
    
    def get_default_mcp_config(self) -> Dict[str, Any]:
        """Get the default MCP server configuration following Cursor format."""
        return {
            "mcpServers": {
                "tmux-mcp-tools": {
                    "command": "uvx",
                    "args": ["tmux-mcp-tools"]
                }
            }
        }
    
    def get_default_prompt(self) -> str:
        """Get the default system prompt."""
        return """You are an AI assistant specifically designed to help users interact with tmux pane.

## Rules

* Observe (capture pane), reason and act (send keys or commands).
* You work PROACTIVELY to call tools and do not ask for human confirmation. Find alternative methods by yourself by interacting with terminal.

## Context
* Target tmux pane is `{target_pane}`. 
"""
    
    def load_mcp_config(self) -> Dict[str, Any]:
        """Load MCP configuration, creating default if it doesn't exist."""
        if not self.mcp_config_path.exists():
            self.save_mcp_config(self.get_default_mcp_config())
        
        try:
            with open(self.mcp_config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load MCP config from {self.mcp_config_path}: {e}")
            return self.get_default_mcp_config()
    
    def save_mcp_config(self, config: Dict[str, Any]) -> None:
        """Save MCP configuration to file."""
        try:
            with open(self.mcp_config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
        except IOError as e:
            print(f"Error: Failed to save MCP config to {self.mcp_config_path}: {e}")
    
    def load_prompt(self) -> str:
        """Load system prompt, creating default if it doesn't exist."""
        if not self.prompt_config_path.exists():
            self.save_prompt(self.get_default_prompt())
        
        try:
            with open(self.prompt_config_path, 'r', encoding='utf-8') as f:
                return f.read()
        except IOError as e:
            print(f"Warning: Failed to load prompt from {self.prompt_config_path}: {e}")
            return self.get_default_prompt()
    
    def save_prompt(self, prompt: str) -> None:
        """Save system prompt to file."""
        try:
            with open(self.prompt_config_path, 'w', encoding='utf-8') as f:
                f.write(prompt)
        except IOError as e:
            print(f"Error: Failed to save prompt to {self.prompt_config_path}: {e}")
    
    def get_mcp_server_config(self, server_name: str = "tmux-mcp-tools") -> Optional[Dict[str, Any]]:
        """Get configuration for a specific MCP server."""
        config = self.load_mcp_config()
        return config.get("mcpServers", {}).get(server_name)
    
    def update_mcp_server_config(self, server_name: str, server_config: Dict[str, Any]) -> None:
        """Update configuration for a specific MCP server."""
        config = self.load_mcp_config()
        if "mcpServers" not in config:
            config["mcpServers"] = {}
        config["mcpServers"][server_name] = server_config
        self.save_mcp_config(config)
    
    def list_config_files(self) -> Dict[str, Path]:
        """List all configuration files and their paths."""
        return {
            "mcp_config": self.mcp_config_path,
            "prompt_config": self.prompt_config_path,
            "config_dir": self.config_dir
        }
    
    def print_config_info(self) -> None:
        """Print information about configuration files."""
        print(f"Config dir: {self.config_dir}")
        print(f"MCP: {self.mcp_config_path} {'✓' if self.mcp_config_path.exists() else '✗'}")
        print(f"Prompt: {self.prompt_config_path} {'✓' if self.prompt_config_path.exists() else '✗'}")