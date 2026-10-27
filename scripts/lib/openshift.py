"""Read the current OpenShift session without saving credentials."""

import json
import subprocess

from lib.sample import require


def oc(*args: str, context: str | None = None, namespace: str | None = None) -> str:
    command = ["oc", "--request-timeout=30s"]
    if context:
        command.extend(["--context", context])
    if namespace:
        command.extend(["--namespace", namespace])
    try:
        result = subprocess.run([*command, *args], capture_output=True, text=True, timeout=40, check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError("OpenShift request timed out; check cluster connectivity and your VPN") from None
    if result.returncode:
        error = result.stderr.lower()
        if any(message in error for message in ("unauthorized", "must be logged", "provide credentials")):
            raise RuntimeError("OpenShift login is missing or expired; run oc login in your terminal")
        if "forbidden" in error:
            raise RuntimeError("OpenShift denied access; check permissions in the selected project")
        # Never dump raw Secret responses, credentials or full API exception bodies.
        raise RuntimeError(f"OpenShift command failed ({args[0]}); check context, resource and connectivity")
    return result.stdout.strip()


def context_info(context: str | None = None) -> dict:
    context = context or oc("config", "current-context")
    view = json.loads(oc("config", "view", "--minify", "-o", "json", context=context))
    require(len(view.get("clusters", [])) == 1, "Expected one cluster in the selected oc context")
    server = view["clusters"][0]["cluster"]["server"]
    require(server.startswith("https://"), "The selected cluster must use HTTPS")
    return {"context": context, "server": server}
