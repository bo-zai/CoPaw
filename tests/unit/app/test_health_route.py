# -*- coding: utf-8 -*-
"""Regression tests for the lightweight API health endpoint."""

import os
from pathlib import Path
import subprocess
import sys


def test_api_health_route_is_registered_and_returns_ok():
    """The app should expose GET /api/health/health without extra deps."""
    repo_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{repo_root / 'tests' / 'fakes'}:{repo_root / 'src'}"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys, types; "
                "from fastapi.testclient import TestClient; "
                "boto3 = types.ModuleType('boto3'); "
                "boto3.client = lambda *args, **kwargs: object(); "
                "sys.modules['boto3'] = boto3; "
                "botocore = types.ModuleType('botocore'); "
                "exceptions = types.ModuleType('botocore.exceptions'); "
                "ClientError = type('ClientError', (Exception,), {}); "
                "exceptions.ClientError = ClientError; "
                "botocore.exceptions = exceptions; "
                "sys.modules['botocore'] = botocore; "
                "sys.modules['botocore.exceptions'] = exceptions; "
                "from swe.app._app import app; "
                "client = TestClient(app, raise_server_exceptions=False); "
                "response = client.get('/api/health/health'); "
                "print(response.status_code, response.text); "
                "raise SystemExit("
                "0 if response.status_code == 200 and "
                "response.json() == {'status': 'ok'} else 1)"
            ),
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
