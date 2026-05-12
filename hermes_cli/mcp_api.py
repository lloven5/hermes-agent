"""
MCP Server Management REST API

Provides HTTP endpoints for managing MCP (Model Context Protocol) servers.
Integrates with mcp_config.py for configuration persistence and mcp_tool.py
for runtime connection management.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

try:
    from pydantic import BaseModel, Field
except ImportError:
    raise ImportError("pydantic is required for MCP REST API: pip install pydantic")

from hermes_cli.mcp_config import (
    _get_mcp_servers,
    _remove_mcp_server,
    _save_mcp_server,
    _probe_single_server,
)
from hermes_cli.config import load_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["MCP"])


# ─── Request/Response Models ───────────────────────────────────────────────────


class MCPServerConfig(BaseModel):
    """MCP server configuration."""
    name: str = Field(..., description="Server name (unique identifier)")
    url: Optional[str] = Field(None, description="HTTP/HTTPS URL for HTTP transport")
    command: Optional[str] = Field(None, description="Command to run for stdio transport")
    args: Optional[List[str]] = Field(default_factory=list, description="Command arguments")
    env: Optional[Dict[str, str]] = Field(None, description="Environment variables")
    headers: Optional[Dict[str, str]] = Field(None, description="HTTP headers")
    transport: str = Field("http", description="Transport type: 'http' or 'stdio'")
    auth: Optional[str] = Field(None, description="Authentication type: 'oauth', 'bearer', etc.")
    enabled: bool = Field(True, description="Whether server is enabled")
    tools: Optional[List[str]] = Field(None, description="Explicit list of tool names to enable")
    timeout: Optional[float] = Field(30.0, description="Connection timeout in seconds")


class MCPServerConfigCreate(BaseModel):
    """Request model for creating a new MCP server."""
    url: Optional[str] = Field(None, description="HTTP/HTTPS URL for HTTP transport")
    command: Optional[str] = Field(None, description="Command to run for stdio transport")
    args: Optional[List[str]] = Field(default_factory=list, description="Command arguments")
    env: Optional[Dict[str, str]] = Field(None, description="Environment variables")
    headers: Optional[Dict[str, str]] = Field(None, description="HTTP headers")
    transport: str = Field("http", description="Transport type: 'http' or 'stdio'")
    auth: Optional[str] = Field(None, description="Authentication type")
    enabled: bool = Field(True, description="Whether server is enabled after creation")
    tools: Optional[List[str]] = Field(None, description="Explicit list of tool names to enable")
    timeout: Optional[float] = Field(30.0, description="Connection timeout in seconds")


class MCPServerConfigUpdate(BaseModel):
    """Request model for updating an existing MCP server."""
    url: Optional[str] = Field(None, description="HTTP/HTTPS URL for HTTP transport")
    command: Optional[str] = Field(None, description="Command to run for stdio transport")
    args: Optional[List[str]] = Field(None, description="Command arguments")
    env: Optional[Dict[str, str]] = Field(None, description="Environment variables")
    headers: Optional[Dict[str, str]] = Field(None, description="HTTP headers")
    transport: Optional[str] = Field(None, description="Transport type: 'http' or 'stdio'")
    auth: Optional[str] = Field(None, description="Authentication type")
    enabled: Optional[bool] = Field(None, description="Whether server is enabled")
    tools: Optional[List[str]] = Field(None, description="Explicit list of tool names to enable")
    timeout: Optional[float] = Field(None, description="Connection timeout in seconds")


class MCPServerResponse(BaseModel):
    """Response model for MCP server details."""
    name: str
    url: Optional[str] = None
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    env: Optional[Dict[str, str]] = None
    headers: Optional[Dict[str, str]] = None
    transport: str = "http"
    auth: Optional[str] = None
    enabled: bool = True
    tools: Optional[List[str]] = None
    timeout: float = 30.0
    connected: bool = False
    tool_count: int = 0


class MCPServerListResponse(BaseModel):
    """Response model for listing MCP servers."""
    servers: List[MCPServerResponse]
    total: int


class MCPToolInfo(BaseModel):
    """Information about a tool exposed by an MCP server."""
    name: str
    description: str


class MCPServerTestResult(BaseModel):
    """Result of testing an MCP server connection."""
    name: str
    success: bool
    connected: bool = False
    tool_count: int = 0
    tools: List[MCPToolInfo] = Field(default_factory=list)
    error: Optional[str] = None


class MCPReloadResult(BaseModel):
    """Result of reloading MCP servers."""
    success: bool
    connected_servers: int
    failed_servers: int
    registered_tools: int
    message: str


class MCPStatusResponse(BaseModel):
    """Overall MCP status."""
    total_servers: int
    connected_servers: int
    disconnected_servers: int
    total_tools: int
    servers: List[MCPServerResponse]


# ─── Helper Functions ──────────────────────────────────────────────────────────


def _config_to_response(name: str, config: dict, connected_servers: Dict[str, Any]) -> MCPServerResponse:
    """Convert server config to response model, enriching with runtime status."""
    server = connected_servers.get(name)
    is_connected = server is not None and getattr(server, 'session', None) is not None
    
    tool_count = 0
    if is_connected:
        if hasattr(server, "_registered_tool_names"):
            tool_count = len(server._registered_tool_names)
        elif hasattr(server, "_tools"):
            tool_count = len(server._tools)
    
    transport = config.get("transport", "http") if "url" in config else "stdio"
    
    return MCPServerResponse(
        name=name,
        url=config.get("url"),
        command=config.get("command"),
        args=config.get("args", []),
        env=config.get("env"),
        headers=config.get("headers"),
        transport=transport,
        auth=config.get("auth"),
        enabled=config.get("enabled", True),
        tools=config.get("tools"),
        timeout=config.get("timeout", 30.0),
        connected=is_connected,
        tool_count=tool_count,
    )


def _get_connected_servers() -> Dict[str, Any]:
    """Get currently connected MCP servers from mcp_tool module."""
    try:
        from tools.mcp_tool import _servers, _lock
        with _lock:
            return dict(_servers)
    except ImportError:
        return {}


def _build_server_config(name: str, body: MCPServerConfigCreate) -> dict:
    """Build a server config dict from request body."""
    config = {}
    
    if body.url is not None:
        config["url"] = body.url
    if body.command is not None:
        config["command"] = body.command
    if body.args is not None:
        config["args"] = body.args
    if body.env is not None:
        config["env"] = body.env
    if body.headers is not None:
        config["headers"] = body.headers
    if body.transport is not None:
        config["transport"] = body.transport
    if body.auth is not None:
        config["auth"] = body.auth
    if body.enabled is not None:
        config["enabled"] = body.enabled
    if body.tools is not None:
        config["tools"] = body.tools
    if body.timeout is not None:
        config["timeout"] = body.timeout
    
    return config


# ─── API Endpoints ─────────────────────────────────────────────────────────────


@router.get("/servers", response_model=MCPServerListResponse)
async def list_mcp_servers():
    """List all configured MCP servers with their status."""
    config = load_config()
    servers_config = _get_mcp_servers(config)
    connected_servers = _get_connected_servers()
    
    servers = [
        _config_to_response(name, cfg, connected_servers)
        for name, cfg in servers_config.items()
    ]
    
    return MCPServerListResponse(
        servers=servers,
        total=len(servers),
    )


@router.get("/servers/{name}", response_model=MCPServerResponse)
async def get_mcp_server(name: str):
    """Get details of a specific MCP server."""
    config = load_config()
    servers_config = _get_mcp_servers(config)
    
    if name not in servers_config:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    
    connected_servers = _get_connected_servers()
    return _config_to_response(name, servers_config[name], connected_servers)


@router.post("/servers/{name}", response_model=MCPServerResponse)
async def add_mcp_server(name: str, body: MCPServerConfigCreate):
    """Add a new MCP server."""
    # Validate name
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Server name cannot be empty")
    if not name.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Server name must be alphanumeric (dashes and underscores allowed)")
    
    # Check if already exists
    config = load_config()
    servers_config = _get_mcp_servers(config)
    if name in servers_config:
        raise HTTPException(status_code=409, detail=f"MCP server '{name}' already exists")
    
    # Validate transport configuration
    if body.command:
        body.transport = "stdio"
    elif not body.url:
        raise HTTPException(status_code=400, detail="Either 'url' or 'command' must be provided")
    
    # Build and save config
    server_config = _build_server_config(name, body)
    _save_mcp_server(name, server_config)
    
    connected_servers = _get_connected_servers()
    return _config_to_response(name, server_config, connected_servers)


@router.put("/servers/{name}", response_model=MCPServerResponse)
async def update_mcp_server(name: str, body: MCPServerConfigUpdate):
    """Update an existing MCP server configuration."""
    config = load_config()
    servers_config = _get_mcp_servers(config)
    
    if name not in servers_config:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    
    # Merge with existing config
    existing = dict(servers_config[name])
    
    if body.url is not None:
        existing["url"] = body.url
    if body.command is not None:
        existing["command"] = body.command
    if body.args is not None:
        existing["args"] = body.args
    if body.env is not None:
        existing["env"] = body.env
    if body.headers is not None:
        existing["headers"] = body.headers
    if body.transport is not None:
        existing["transport"] = body.transport
    if body.auth is not None:
        existing["auth"] = body.auth
    if body.enabled is not None:
        existing["enabled"] = body.enabled
    if body.tools is not None:
        existing["tools"] = body.tools
    if body.timeout is not None:
        existing["timeout"] = body.timeout
    
    _save_mcp_server(name, existing)
    
    connected_servers = _get_connected_servers()
    return _config_to_response(name, existing, connected_servers)


@router.delete("/servers/{name}")
async def remove_mcp_server(name: str):
    """Remove an MCP server."""
    config = load_config()
    servers_config = _get_mcp_servers(config)
    
    if name not in servers_config:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    
    # Disconnect if connected
    try:
        from tools.mcp_tool import _servers, _lock
        with _lock:
            if name in _servers:
                server = _servers[name]
                try:
                    asyncio.get_event_loop().run_until_complete(server.shutdown())
                except Exception:
                    pass
                del _servers[name]
    except ImportError:
        pass
    
    # Remove from config
    _remove_mcp_server(name)
    
    return {"message": f"MCP server '{name}' removed successfully"}


@router.post("/servers/{name}/test")
async def test_mcp_server(name: str, timeout: float = 30.0):
    """Test connection to an MCP server and list its tools."""
    config = load_config()
    servers_config = _get_mcp_servers(config)
    
    if name not in servers_config:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    
    server_config = servers_config[name]
    
    try:
        tools_found = _probe_single_server(name, server_config, connect_timeout=timeout)
        tools = [
            MCPToolInfo(name=t[0], description=t[1])
            for t in tools_found
        ]
        return MCPServerTestResult(
            name=name,
            success=True,
            connected=True,
            tool_count=len(tools),
            tools=tools,
        )
    except Exception as exc:
        error_message = str(exc)
        if "401" in error_message or "unauthorized" in error_message.lower():
            error_message = "Authentication failed - check your credentials"
        elif "connection refused" in error_message.lower():
            error_message = "Connection refused - server may be down or unreachable"
        elif "timeout" in error_message.lower():
            error_message = "Connection timed out - server took too long to respond"
        
        return MCPServerTestResult(
            name=name,
            success=False,
            connected=False,
            error=error_message,
        )


@router.post("/servers/{name}/connect")
async def connect_mcp_server(name: str, timeout: float = 30.0):
    """Connect to an MCP server and register its tools.
    
    This is primarily useful for stdio servers which are not connected by default.
    HTTP servers are typically connected automatically on startup.
    """
    config = load_config()
    servers_config = _get_mcp_servers(config)
    
    if name not in servers_config:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    
    try:
        from tools.mcp_tool import _servers, _lock, register_mcp_servers, _ensure_mcp_loop
        import asyncio
        
        with _lock:
            if name in _servers:
                server = _servers[name]
                if server.session is not None:
                    return MCPServerResponse(
                        name=name,
                        url=servers_config[name].get("url"),
                        command=servers_config[name].get("command"),
                        args=servers_config[name].get("args", []),
                        env=servers_config[name].get("env"),
                        headers=servers_config[name].get("headers"),
                        transport=servers_config[name].get("transport", "stdio"),
                        auth=servers_config[name].get("auth"),
                        enabled=servers_config[name].get("enabled", True),
                        tools=servers_config[name].get("tools"),
                        timeout=servers_config[name].get("timeout", 30.0),
                        connected=True,
                        tool_count=len(getattr(server, "_registered_tool_names", [])),
                    )
        
        # Start the MCP event loop
        _ensure_mcp_loop()
        
        # Connect to the server
        server_config = servers_config[name]
        server_config["connect_timeout"] = timeout
        
        from tools.mcp_tool import _discover_and_register_server
        tool_names = await _discover_and_register_server(name, server_config)
        
        # Return success response
        return {
            "name": name,
            "success": True,
            "connected": True,
            "tool_count": len(tool_names),
            "tools": tool_names,
            "message": f"Successfully connected to '{name}' with {len(tool_names)} tools"
        }
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"MCP module not available: {exc}")
    except Exception as exc:
        return {
            "name": name,
            "success": False,
            "connected": False,
            "tool_count": 0,
            "error": str(exc),
        }


@router.post("/servers/{name}/disconnect")
async def disconnect_mcp_server(name: str):
    """Disconnect an MCP server and unregister its tools."""
    config = load_config()
    servers_config = _get_mcp_servers(config)
    
    if name not in servers_config:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    
    try:
        from tools.mcp_tool import _servers, _lock
        import asyncio
        
        with _lock:
            if name not in _servers:
                return {
                    "name": name,
                    "success": True,
                    "connected": False,
                    "message": f"MCP server '{name}' was not connected"
                }
            
            server = _servers[name]
        
        # Shutdown the server
        loop = asyncio.get_event_loop()
        loop.run_until_complete(server.shutdown())
        
        with _lock:
            del _servers[name]
        
        return {
            "name": name,
            "success": True,
            "connected": False,
            "message": f"Successfully disconnected '{name}'"
        }
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"MCP module not available: {exc}")
    except Exception as exc:
        return {
            "name": name,
            "success": False,
            "connected": False,
            "error": str(exc),
        }


@router.get("/servers/{name}/status")
async def get_mcp_server_status(name: str):
    """Get the connection status of an MCP server."""
    config = load_config()
    servers_config = _get_mcp_servers(config)
    
    if name not in servers_config:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    
    server_config = servers_config[name]
    connected_servers = _get_connected_servers()
    
    server = connected_servers.get(name)
    is_connected = server is not None and getattr(server, 'session', None) is not None
    
    tool_count = 0
    if is_connected:
        tool_count = len(getattr(server, "_registered_tool_names", []))
    
    return {
        "name": name,
        "connected": is_connected,
        "tool_count": tool_count,
        "transport": server_config.get("transport", "http") if "url" in server_config else "stdio",
        "enabled": server_config.get("enabled", True),
    }


@router.get("/servers/{name}/tools")
async def get_mcp_tools(name: str):
    """Get the list of tools exposed by an MCP server."""
    config = load_config()
    servers_config = _get_mcp_servers(config)
    
    if name not in servers_config:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    
    connected_servers = _get_connected_servers()
    server = connected_servers.get(name)
    
    if not server or getattr(server, 'session', None) is None:
        raise HTTPException(
            status_code=503,
            detail=f"MCP server '{name}' is not currently connected"
        )
    
    tools = []
    for t in getattr(server, "_tools", []):
        tools.append(MCPToolInfo(
            name=t.name,
            description=getattr(t, "description", "") or "",
        ))
    
    return {
        "name": name,
        "tools": tools,
        "total": len(tools),
    }


@router.post("/reload", response_model=MCPReloadResult)
async def reload_mcp_servers():
    """Reload all MCP servers: disconnect all, re-read config, reconnect."""
    try:
        from tools.mcp_tool import (
            shutdown_mcp_servers,
            discover_mcp_tools,
            get_mcp_status,
        )
        
        # Disconnect all existing connections
        shutdown_mcp_servers()
        
        # Re-discover and reconnect
        tool_names = discover_mcp_tools()
        
        # Get updated status
        status = get_mcp_status()
        connected = [s for s in status if s.get("connected")]
        failed = len(status) - len(connected)
        
        return MCPReloadResult(
            success=True,
            connected_servers=len(connected),
            failed_servers=failed,
            registered_tools=len(tool_names),
            message=f"Reloaded {len(connected)} server(s), registered {len(tool_names)} tool(s)"
        )
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"MCP support not available: {exc}"
        )
    except Exception as exc:
        logger.error("Failed to reload MCP servers: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload MCP servers: {str(exc)}"
        )


@router.get("/status", response_model=MCPStatusResponse)
async def get_mcp_status():
    """Get overall MCP connection status."""
    try:
        from tools.mcp_tool import get_mcp_status as _get_runtime_status
        
        status = _get_runtime_status()
        connected_servers = {s["name"]: s for s in status if s.get("connected")}
        
        config = load_config()
        servers_config = _get_mcp_servers(config)
        
        servers = [
            _config_to_response(name, cfg, connected_servers)
            for name, cfg in servers_config.items()
        ]
        
        total_connected = len([s for s in status if s.get("connected")])
        
        return MCPStatusResponse(
            total_servers=len(servers_config),
            connected_servers=total_connected,
            disconnected_servers=len(servers_config) - total_connected,
            total_tools=sum(s.tool_count for s in servers),
            servers=servers,
        )
    except ImportError:
        # MCP module not available
        return MCPStatusResponse(
            total_servers=0,
            connected_servers=0,
            disconnected_servers=0,
            total_tools=0,
            servers=[],
        )


# ─── Tool-level Endpoints ──────────────────────────────────────────────────────


@router.get("/tools")
async def list_all_mcp_tools():
    """Get list of all MCP tools from all connected servers."""
    try:
        from tools.mcp_tool import _servers, _lock
        
        all_tools = []
        with _lock:
            for name, server in _servers.items():
                for t in getattr(server, "_tools", []):
                    all_tools.append({
                        "server": name,
                        "name": t.name,
                        "description": getattr(t, "description", "") or "",
                    })
        
        return {
            "tools": all_tools,
            "total": len(all_tools),
            "servers_connected": len(_servers),
        }
    except ImportError:
        return {"tools": [], "total": 0, "servers_connected": 0}