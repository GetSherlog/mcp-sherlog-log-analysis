"""Central session & utility helpers for LogAI FastMCP server.

This module owns the FastMCP *app* instance plus the in-memory scratch-pad
(`session_vars`) that lets individual tool calls communicate with each other.
All other modules should *only* import what they need from here instead of
instantiating additional `FastMCP` objects.
"""

from typing import Any, Dict, List
import logging
import dill
import pickle
from pathlib import Path
import atexit

import nltk
import nltk.downloader
from mcp.server.fastmcp import FastMCP
from logai_mcp.config import get_settings

# Configure FastMCP for Sherlog Canvas web application usage
# stateless_http=True makes it suitable for multi-node deployments
app = FastMCP(name="LogAIMCP", stateless_http=True)

# Add health check endpoint
@app.custom_route("/health", methods=["GET"])
async def health_check(request):
    from starlette.responses import JSONResponse
    return JSONResponse({"status": "ok", "service": "LogAI MCP"})

for _resource in [
    "tokenizers/punkt",
    "corpora/wordnet",
    "taggers/averaged_perceptron_tagger",
]:
    try:
        nltk.data.find(_resource)
    except LookupError:
        nltk.download(_resource.split("/")[-1], quiet=True)

session_vars: Dict[str, Any] = {}
session_meta: Dict[str, Dict[str, Any]] = {}

logger = logging.getLogger("LogAIMCP")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(_handler)

settings = get_settings()
logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

# Session persistence
SESSION_FILE = Path("session_state.pkl")

def save_session():
    """Save current session state"""
    try:
        from logai_mcp.ipython_shell_utils import _SHELL
        
        state = {
            'session_vars': session_vars,
            'session_meta': session_meta,
            'user_ns': {k: v for k, v in _SHELL.user_ns.items() 
                       if not k.startswith('_') and k not in {'In', 'Out', 'exit', 'quit', 'get_ipython'}}
        }
        
        with open(SESSION_FILE, 'wb') as f:
            dill.dump(state, f)
            
        logger.info(f"Session saved to {SESSION_FILE}")
        
    except Exception as e:
        logger.error(f"Session save failed: {e}")

def restore_session():
    """Restore session state if backup exists"""
    if not SESSION_FILE.exists():
        return
        
    try:
        from logai_mcp.ipython_shell_utils import _SHELL
        
        with open(SESSION_FILE, 'rb') as f:
            state = dill.load(f)
            
        session_vars.clear()
        session_vars.update(state.get('session_vars', {}))
        
        session_meta.clear() 
        session_meta.update(state.get('session_meta', {}))
        
        _SHELL.user_ns.update(state.get('user_ns', {}))
        
        logger.info("Session restored")
        
    except Exception as e:
        logger.error(f"Session restore failed: {e}")

# Auto-save on shutdown
atexit.register(save_session)