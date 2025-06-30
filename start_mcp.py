#!/usr/bin/env python3
"""
Simple startup script for TIDAL MCP server
"""
import sys
import os

# Add current directory to Python path
sys.path.append('.')

# Import and run the MCP server
from mcp_server.server import mcp

if __name__ == "__main__":
    print('Starting TIDAL MCP server...')
    mcp.run()