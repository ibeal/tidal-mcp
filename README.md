# TIDAL MCP: My Custom Picks 🌟🎧

![Demo: Music Recommendations in Action](./assets/tidal_mcp_demo.gif)

Most music platforms offer recommendations — Daily Discovery, Top Artists, New Arrivals, etc. — but even with the state-of-the-art system, they often feel too "aggregated". I wanted something more custom and context-aware.

With TIDAL MCP, you can ask for things like:
> *"Based on my last 10 favorites, find similar tracks — but only ones from recent years."*
>
> *"Find me tracks like those in this playlist, but slower and more acoustic."*

The LLM filters and curates results using your input, finds similar tracks via TIDAL’s API, and builds new playlists directly in your account.

<a href="https://glama.ai/mcp/servers/@yuhuacheng/tidal-mcp">
  <img width="400" height="200" src="https://glama.ai/mcp/servers/@yuhuacheng/tidal-mcp/badge" alt="TIDAL: My Custom Picks MCP server" />
</a>

## Features

- 🌟 **Music Recommendations**: Get personalized track recommendations based on your listening history **plus your custom criteria**.
- ၊၊||၊ **Playlist Management**: Create, view, and manage your TIDAL playlists

## Quick Start

### Prerequisites

- Python 3.10+ OR Docker
- [uv](https://github.com/astral-sh/uv) (Python package manager) - only needed for non-Docker installation
- TIDAL subscription

### Installation

#### Option 1: Docker (Recommended)

1. Clone this repository:
   ```bash
   git clone https://github.com/yuhuacheng/tidal-mcp.git
   cd tidal-mcp
   ```

2. Build and run with Docker Compose:
   ```bash
   docker-compose up -d
   ```

   Or with Docker directly:
   ```bash
   docker build -t tidal-mcp .
   docker run -d -p 5050:5050 --name tidal-mcp tidal-mcp
   ```

   The server will be available at `http://localhost:5050`.

3. To customize the port, edit the `TIDAL_MCP_PORT` environment variable in `docker-compose.yml` or pass it to docker run:
   ```bash
   docker run -d -p 5100:5100 -e TIDAL_MCP_PORT=5100 --name tidal-mcp tidal-mcp
   ```

#### Option 2: Local Python Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yuhuacheng/tidal-mcp.git
   cd tidal-mcp
   ```

2. Create a virtual environment and install dependencies using uv:
   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install the package with all dependencies from the pyproject.toml file:
   ```bash
   uv pip install --editable .
   ```

   This will install all dependencies defined in the pyproject.toml file and set up the project in development mode.


## MCP Client Configuration

### Claude Desktop Configuration

To add this MCP server to Claude Desktop, you need to update the MCP configuration file.

#### Option 1: Docker Configuration (if using Docker)

```json
{
  "mcpServers": {
    "TIDAL Integration": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--network",
        "host",
        "-v",
        "/tmp:/tmp",
        "tidal-mcp"
      ],
      "env": {
        "TIDAL_MCP_PORT": "5050"
      }
    }
  }
}
```

**Setup:**

1. Build the Docker image:
   ```bash
   docker build -t tidal-mcp .
   ```

2. Authenticate with TIDAL (run this once):
   ```bash
   docker-compose -f docker-compose.auth.yml run --rm tidal-auth
   ```

   You'll see the OAuth URL in the output:
   ```
   ============================================================
   TIDAL LOGIN REQUIRED
   Please open this URL in your browser:

   https://link.tidal.com/XXXXX

   Expires in 300 seconds
   ============================================================
   ```

   Open the URL in your browser, log in to TIDAL, and the session will be saved to `/tmp/tidal-session-oauth.json`.

3. Update your Claude Desktop config (see above) and restart Claude Desktop.

**Configuration details:**
- `--network host` - Allows the container to use the host's network directly
- `-v /tmp:/tmp` - Mounts the host's /tmp directory so the TIDAL session persists across container restarts

To use a custom port:
```json
{
  "mcpServers": {
    "TIDAL Integration": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--network",
        "host",
        "-v",
        "/tmp:/tmp",
        "-e",
        "TIDAL_MCP_PORT=5100",
        "tidal-mcp"
      ]
    }
  }
}
```

#### Option 2: Local Python Configuration (if not using Docker)

```json
{
  "mcpServers": {
    "TIDAL Integration": {
      "command": "/path/to/your/uv",
      "env": {
        "TIDAL_MCP_PORT": "5100"
      },
      "args": [
        "run",
        "--with",
        "requests",
        "--with",
        "mcp[cli]",
        "--with",
        "flask",
        "--with",
        "tidalapi",
        "mcp",
        "run",
        "/path/to/your/project/tidal-mcp/mcp_server/server.py"
      ]
    }
  }
}
```

Example scrrenshot of the MCP configuration in Claude Desktop:
![Claude MCP Configuration](./assets/claude_desktop_config.png)

### Steps to Install MCP Configuration

1. Open Claude Desktop
2. Go to Settings > Developer
3. Click on "Edit Config"
4. Paste the modified JSON configuration
5. Save the configuration
6. Restart Claude Desktop

## Suggested Prompt Starters
Once configured, you can interact with your TIDAL account through a LLM by asking questions like:

- *“Recommend songs like those in this playlist, but slower and more acoustic.”*
- *“Create a playlist based on my top tracks, but focused on chill, late-night vibes.”*
- *“Find songs like these in playlist XYZ but in languages other than English.”*

*💡 You can also ask the model to:*
- Use more tracks as seeds to broaden the inspiration.
- Return more recommendations if you want a longer playlist.
- Or delete a playlist if you’re not into it — no pressure!

## Available Tools

The TIDAL MCP integration provides the following tools:

- `tidal_login`: Authenticate with TIDAL through browser login flow
- `get_favorite_tracks`: Retrieve your favorite tracks from TIDAL
- `recommend_tracks`: Get personalized music recommendations
- `create_tidal_playlist`: Create a new playlist in your TIDAL account
- `get_user_playlists`: List all your playlists on TIDAL
- `get_playlist_tracks`: Retrieve all tracks from a specific playlist
- `delete_tidal_playlist`: Delete a playlist from your TIDAL account

## License

[MIT License](LICENSE)

## Acknowledgements

- [Model Context Protocol (MCP)](https://github.com/modelcontextprotocol/python-sdk)
- [TIDAL Python API](https://github.com/tamland/python-tidal)