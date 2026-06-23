"""Execute C# on the .NET Interactive kernel via the live Jupyter Server.

The CI workflow starts the built image as a container serving JupyterLab on
:8888 with an empty token, then runs this directory with pytest. Rather than
drive the Lab UI (flaky), we talk to the Jupyter kernel REST + websocket API
directly.

We cover two distinct paths:
  * the `.net-csharp` kernel, which compiles C# in-process via Roslyn (notebook
    use); and
  * the `dotnet` SDK command-line tools (terminal / VSCode use: `dotnet new`,
    `dotnet run`, `csc`), exercised by shelling out from a `python3` kernel that
    runs inside the container.
"""
import json
import textwrap
import uuid

import pytest
import requests
from websocket import create_connection

JUPYTER_URL = "http://localhost:8888"
WS_URL = "ws://localhost:8888"
KERNEL_NAME = ".net-csharp"

# The .NET Interactive kernel is slow to cold-start, and a cold `dotnet new` +
# `dotnet run` does a NuGet restore, so the per-recv (cell-silence) timeout is
# generous: a long-running cell sends no messages until it completes.
KERNEL_START_TIMEOUT = 120  # s
EXECUTE_TIMEOUT = 300       # s


@pytest.fixture(scope="module")
def session():
    """A requests session primed with the server's XSRF token.

    Jupyter Server enforces XSRF on mutating requests (POST/DELETE) even when
    the token is empty, so we fetch the `_xsrf` cookie via a GET first and send
    it back as a header on subsequent calls.
    """
    s = requests.Session()
    s.get(f"{JUPYTER_URL}/", timeout=30)
    xsrf = s.cookies.get("_xsrf")
    if xsrf:
        s.headers["X-XSRFToken"] = xsrf
    return s


def _execute(kernel_id, code):
    """Run `code` on the kernel and return concatenated stdout stream text."""
    ws = create_connection(
        f"{WS_URL}/api/kernels/{kernel_id}/channels",
        timeout=EXECUTE_TIMEOUT,
    )
    msg_id = uuid.uuid4().hex
    try:
        ws.send(json.dumps({
            "header": {
                "msg_id": msg_id,
                "username": "test",
                "session": uuid.uuid4().hex,
                "msg_type": "execute_request",
                "version": "5.3",
            },
            "parent_header": {},
            "metadata": {},
            "content": {
                "code": code,
                "silent": False,
                "store_history": True,
                "user_expressions": {},
                "allow_stdin": False,
                "stop_on_error": True,
            },
            "channel": "shell",
        }))

        stdout = ""
        while True:
            msg = json.loads(ws.recv())
            if msg.get("parent_header", {}).get("msg_id") != msg_id:
                continue
            msg_type = msg["msg_type"]
            content = msg["content"]
            if msg_type == "stream" and content.get("name") == "stdout":
                stdout += content.get("text", "")
            elif msg_type == "error":
                pytest.fail("C# kernel returned an error: " + "\n".join(content.get("traceback", [])))
            elif msg_type == "status" and content.get("execution_state") == "idle":
                break
        return stdout
    finally:
        ws.close()


def _start_kernel(session, name):
    resp = session.post(
        f"{JUPYTER_URL}/api/kernels",
        json={"name": name},
        timeout=KERNEL_START_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["id"]


@pytest.fixture(scope="module")
def kernel_id(session):
    kid = _start_kernel(session, KERNEL_NAME)
    yield kid
    session.delete(f"{JUPYTER_URL}/api/kernels/{kid}", timeout=30)


@pytest.fixture(scope="module")
def python_kernel_id(session):
    kid = _start_kernel(session, "python3")
    yield kid
    session.delete(f"{JUPYTER_URL}/api/kernels/{kid}", timeout=30)


def test_csharp_kernel_registered(session):
    """The .NET (C#) kernelspec is installed and discoverable."""
    resp = session.get(f"{JUPYTER_URL}/api/kernelspecs", timeout=30)
    resp.raise_for_status()
    assert KERNEL_NAME in resp.json()["kernelspecs"]


def test_csharp_compiles_and_runs(kernel_id):
    """A small C# program compiles and runs on the .NET (C#) kernel."""
    out = _execute(kernel_id, 'int Add(int a, int b) => a + b;\nConsole.WriteLine($"2 + 3 = {Add(2, 3)}");')
    assert "2 + 3 = 5" in out


def test_dotnet_sdk_version(python_kernel_id):
    """The `dotnet` SDK CLI is on PATH inside the container at the pinned major."""
    out = _execute(python_kernel_id, textwrap.dedent("""
        import subprocess
        r = subprocess.run(["dotnet", "--version"], capture_output=True, text=True)
        print("DOTNET_VERSION:" + r.stdout.strip())
    """))
    assert "DOTNET_VERSION:10." in out


def test_dotnet_sdk_builds_and_runs_console_app(python_kernel_id):
    """`dotnet new console` + `dotnet run` produces a working executable.

    This is the terminal/VSCode path students use, distinct from the in-process
    Roslyn compilation the notebook kernel performs.
    """
    code = textwrap.dedent("""
        import subprocess, tempfile, sys
        d = tempfile.mkdtemp()
        new = subprocess.run(["dotnet", "new", "console", "-o", d],
                             capture_output=True, text=True)
        if new.returncode != 0:
            print("NEW_FAILED:" + new.stdout + new.stderr); sys.exit()
        run = subprocess.run(["dotnet", "run", "--project", d],
                             capture_output=True, text=True)
        print("RUN_RC:" + str(run.returncode))
        print("RUN_OUT:" + run.stdout.strip())
        print("RUN_ERR:" + run.stderr.strip())
    """)
    out = _execute(python_kernel_id, code)
    assert "RUN_RC:0" in out, out
    assert "Hello, World!" in out, out