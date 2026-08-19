# -*- coding: utf-8 -*-
"""
Command probing utilities — check if commands are installed and working.
Simplified version from agent-reach for Google Maps scraper.
"""

import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ProbeResult:
    """Result of probing a command."""
    status: str  # "ok", "missing", "broken", "timeout", "error"
    ok: bool
    output: str
    hint: str
    
    
def probe_command(
    command: str,
    args: List[str],
    timeout: int = 10,
    package: Optional[str] = None,
) -> ProbeResult:
    """
    Probe if a command is installed and working.
    
    Args:
        command: Command to run
        args: Arguments to pass
        timeout: Timeout in seconds
        package: Optional package name for install hint
    
    Returns:
        ProbeResult with status and diagnostic info
    """
    # Check if command exists
    if not shutil.which(command):
        hint = f"Install {package or command}: pip install {package or command}"
        return ProbeResult(
            status="missing",
            ok=False,
            output="",
            hint=hint,
        )
    
    # Try to run it
    try:
        result = subprocess.run(
            [command] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        
        if result.returncode == 0:
            return ProbeResult(
                status="ok",
                ok=True,
                output=result.stdout,
                hint="",
            )
        else:
            return ProbeResult(
                status="error",
                ok=False,
                output=result.stderr,
                hint=f"Command failed: {result.stderr[:200]}",
            )
    
    except subprocess.TimeoutExpired:
        return ProbeResult(
            status="timeout",
            ok=False,
            output="",
            hint=f"Command timed out after {timeout}s",
        )
    
    except Exception as e:
        return ProbeResult(
            status="broken",
            ok=False,
            output="",
            hint=f"Command exists but cannot execute: {str(e)}",
        )
