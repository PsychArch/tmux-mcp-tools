#!/usr/bin/env python3
import asyncio
import argparse
import os
import json
import sys
from typing import Optional, List, Dict, Any, Tuple
from contextlib import AsyncExitStack

# MCP client SDK
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# OpenAI client for OpenRouter
from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessage

# Configuration management
from .config import ConfigManager

# Default model to use with OpenRouter
DEFAULT_MODEL = "google/gemini-2.5-pro-preview"

# Default enter delay
DEFAULT_ENTER_DELAY = "0.4"

def convert_tool_format(tool):
    """Convert MCP tool definitions to OpenAI tool definitions"""
    converted_tool = {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": tool.inputSchema["properties"],
                "required": tool.inputSchema.get("required", [])
            }
        }
    }
    return converted_tool

# Component 1: LLM Response Handler
class LLMResponseHandler:
    """Handles responses from the LLM, including parsing messages and tool calls"""
    
    def __init__(self, model: str = DEFAULT_MODEL, **model_kwargs):
        self.model = model
        self.openai = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY")
        )
        self.target_pane = model_kwargs.get('target_pane', '0')
        
        # Load system prompt from configuration
        config_manager = ConfigManager()
        prompt_template = config_manager.load_prompt()
        self.system_prompt = prompt_template.format(target_pane=self.target_pane)
        
        self.messages = [
            {
                "role": "system",
                "content": self.system_prompt
            }
        ]
    
    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation history"""
        self.messages.append({
            "role": "user",
            "content": content
        })
    
    def add_tool_result(self, tool_call_id: str, tool_name: str, content: str) -> None:
        """Add a tool result to the conversation history"""
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": content
        })
    
    def add_assistant_message(self, message: Dict[str, Any]) -> None:
        """Add an assistant message to the conversation history"""
        self.messages.append(message)
    
    async def get_llm_response(self, tools: List[Dict[str, Any]] = None) -> ChatCompletionMessage:
        """Get a response from the LLM with optional tools"""
        kwargs = {
            "model": self.model,
            "messages": self.messages
        }
        
        if tools:
            kwargs["tools"] = tools
        
        response = self.openai.chat.completions.create(**kwargs)
        message = response.choices[0].message
        
        # Add the response to the conversation history
        self.add_assistant_message(message.model_dump())
        
        return message


# Component 2: Tool Call Executor
class ToolCallExecutor:
    """Executes tool calls and handles their results"""
    
    def __init__(self, sessions: Dict[str, ClientSession], target_pane: str = "0"):
        self.sessions = sessions  # Map of server_name -> session
        self.target_pane = target_pane
        self.tool_to_server = {}  # Map of tool_name -> server_name
    
    async def initialize(self):
        """Initialize the tool mapping after construction"""
        await self._build_tool_mapping()
    
    async def _build_tool_mapping(self):
        """Build mapping of tool names to server names"""
        for server_name, session in self.sessions.items():
            try:
                response = await session.list_tools()
                for tool in response.tools:
                    self.tool_to_server[tool.name] = server_name
            except Exception as e:
                print(f"Warning: Failed to list tools for server {server_name}: {e}")
    
    async def execute_tool_call(self, tool_call) -> Tuple[str, Any]:
        """Execute a tool call and return the result"""
        tool_name = tool_call.function.name
        tool_args = tool_call.function.arguments
        tool_args = json.loads(tool_args) if tool_args else {}
        
        # Set target pane if not specified
        if "target_pane" in tool_args and not tool_args["target_pane"]:
            tool_args["target_pane"] = self.target_pane

        # Find which server has this tool
        server_name = self.tool_to_server.get(tool_name)
        if not server_name:
            error_msg = f"Tool {tool_name} not found in any connected server"
            print(error_msg)
            return error_msg, {"content": error_msg}
        
        session = self.sessions[server_name]
        
        # Execute tool call
        try:
            result = await session.call_tool(tool_name, tool_args)
            log_message = f"[Calling tool {tool_name} on server {server_name} with args {tool_args}]"
        except Exception as e:
            error_msg = f"Error calling tool {tool_name} on server {server_name}: {e}"
            print(error_msg)
            result = {"content": error_msg}
            log_message = error_msg
        
        return log_message, result


# Component 3: User Interaction Manager
class UserInteractionManager:
    """Manages user input and output"""
    
    def __init__(self):
        self.exit_requested = False
    
    def get_user_input(self) -> str:
        """Get input from the user"""
        try:
            query = input("Request: ").strip()
            if query.lower() == '':
                self.exit_requested = True
            return query
        except EOFError:
            self.exit_requested = True
            return ""
    
    def display_result(self, result: str) -> None:
        """Display a result to the user"""
        if result:
            print("Agent: ", result)
    
    def should_exit(self) -> bool:
        """Check if the user has requested to exit"""
        return self.exit_requested


# Main Agent Class
class TmuxAgent:
    """Agent that can connect to multiple MCP servers"""
    
    def __init__(self, target_pane: str = "0", model: str = DEFAULT_MODEL, enter_delay: str = DEFAULT_ENTER_DELAY):
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        self.target_pane = target_pane
        self.model = model
        self.enter_delay = enter_delay
        self.available_tools = []
        
        # Initialize configuration manager
        self.config_manager = ConfigManager()
        
        # Initialize components
        self.llm_handler = LLMResponseHandler(model=model, target_pane=target_pane)
        self.user_manager = UserInteractionManager()
        # Tool executor will be initialized after connecting to servers
        self.tool_executor = None

    async def connect_to_servers(self):
        """Connect to all enabled MCP servers"""
        enabled_servers = self.config_manager.get_enabled_mcp_servers()
        
        if not enabled_servers:
            print("No enabled MCP servers found in configuration")
            return False
        
        connected_servers = 0
        for server_name, server_config in enabled_servers.items():
            try:
                await self._connect_to_server(server_name, server_config)
                connected_servers += 1
                print(f"✓ {server_name}")
            except Exception as e:
                print(f"✗ {server_name}: {e}")
        
        if connected_servers == 0:
            print("Failed to connect to any MCP servers")
            return False
        
        # Initialize the tool executor with all connected sessions
        self.tool_executor = ToolCallExecutor(self.sessions, self.target_pane)
        await self.tool_executor.initialize()
        
        # Collect all available tools from all servers
        await self._collect_all_tools()
        
        return True

    async def _connect_to_server(self, server_name: str, server_config: Dict[str, Any]):
        """Connect to a single MCP server"""
        # Update server config to include enter_delay for tmux-mcp-tools
        config_copy = dict(server_config)
        
        # We need to adjust the args to include the enter_delay parameter
        args_copy = list(config_copy.get("args", []))
        args_copy.extend(["--enter-delay", self.enter_delay])
        config_copy["args"] = args_copy
        
        server_params = StdioServerParameters(**config_copy)
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        stdio, write = stdio_transport
        session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))

        await session.initialize()
        
        # Store the session
        self.sessions[server_name] = session

    async def _collect_all_tools(self):
        """Collect all available tools from all connected servers"""
        self.available_tools = []
        
        for server_name, session in self.sessions.items():
            try:
                response = await session.list_tools()
                server_tools = [convert_tool_format(tool) for tool in response.tools]
                self.available_tools.extend(server_tools)
            except Exception as e:
                print(f"Warning: Failed to list tools for {server_name}: {e}")

    async def process_llm_response(self, message: ChatCompletionMessage) -> Tuple[str, bool]:
        """Process an LLM response, handling any tool calls"""
        result_texts = []
        has_tool_calls = False
        
        # Add assistant message content if it exists
        if message.content:
            result_texts.append(message.content)
        
        # Process tool calls if any
        if message.tool_calls:
            has_tool_calls = True
            for tool_call in message.tool_calls:
                # Execute the tool call
                log_message, result = await self.tool_executor.execute_tool_call(tool_call)
                result_texts.append(log_message)
                
                # Add tool result to conversation history
                content = result.content if hasattr(result, "content") else str(result)
                self.llm_handler.add_tool_result(tool_call.id, tool_call.function.name, content)
        
        return "\n".join(result_texts), has_tool_calls

    async def run(self):
        """Run the agent"""
    
        # Get initial user input
        user_input = self.user_manager.get_user_input()
        if self.user_manager.should_exit():
            return
        
        # Add initial user message
        self.llm_handler.add_user_message(user_input)
        
        # Main interaction loop
        while True:
            message = await self.llm_handler.get_llm_response(self.available_tools)
            result, has_tool_calls = await self.process_llm_response(message)
            self.user_manager.display_result(result)
            if has_tool_calls:
                continue
            user_input = self.user_manager.get_user_input()
            if self.user_manager.should_exit():
                break
            self.llm_handler.add_user_message(user_input)

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Tmux Agent with MCP Tools")
    parser.add_argument("--target", dest="target_pane", default="0", 
                        help="Target tmux pane (default: 0)")
    parser.add_argument("--model", dest="model", default=DEFAULT_MODEL,
                        help=f"LLM model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--enter-delay", dest="enter_delay", default=DEFAULT_ENTER_DELAY,
                        help=f"Delay in seconds before sending Enter key, or 'infinite' for manual confirmation (default: {DEFAULT_ENTER_DELAY})")
    parser.add_argument("--config-info", action="store_true",
                        help="Show configuration file information and exit")
    args = parser.parse_args()
    
    # Initialize configuration manager
    config_manager = ConfigManager()
    
    # Show config info if requested
    if args.config_info:
        config_manager.print_config_info()
        return
    
    # Initialize and run the agent
    agent = TmuxAgent(target_pane=args.target_pane, model=args.model, enter_delay=args.enter_delay)
    try:
        success = await agent.connect_to_servers()
        if success:
            await agent.run()
        else:
            print("Failed to connect to servers. Exiting.")
    finally:
        try:
            await agent.cleanup()
        except Exception as e:
            print(f"\nError during cleanup: {str(e)}")

def run_main():
    asyncio.run(main())

if __name__ == "__main__":
    run_main()