#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / ".weekly-email.env"
DEFAULT_KEYCHAIN_SERVICE = "farmhannong-weekly-email"
KEYCHAIN_ACCOUNTS = [
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SUMMARY_EMAIL_RECIPIENTS",
    "SITE_URL",
]


def load_env_file(path: Path) -> dict[str, str]:
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        loaded[key] = value
    return loaded


def read_keychain_value(service: str, account: str) -> str:
    result = subprocess.run(
        ["security", "find-generic-password", "-w", "-s", service, "-a", account],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def build_runtime_env(config_path: Path, keychain_service: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(load_env_file(config_path))
    for account in KEYCHAIN_ACCOUNTS:
        if env.get(account):
            continue
        keychain_value = read_keychain_value(keychain_service, account)
        if keychain_value:
            env[account] = keychain_value
    env["REQUIRE_WEEKLY_EMAIL_RECIPIENTS"] = "1"
    return env


def run_checked(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify the current public Farmhannong week and send the weekly email locally from this Mac."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to a local env file with SMTP and recipient settings.")
    parser.add_argument(
        "--keychain-service",
        default=os.getenv("FARMHANNONG_WEEKLY_EMAIL_KEYCHAIN_SERVICE", DEFAULT_KEYCHAIN_SERVICE),
        help="macOS Keychain service name used when a setting is missing from the env file.",
    )
    parser.add_argument("--preview-only", action="store_true", help="Generate the weekly email preview assets locally without sending email.")
    parser.add_argument("--recipients", help="Optional comma-separated override recipients for a manual test send.")
    parser.add_argument("--skip-verify", action="store_true", help="Skip the public current-week verification step.")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser()
    env = build_runtime_env(config_path, args.keychain_service)

    verify_result = None
    if not args.skip_verify:
        verify_result = run_checked(
            ["node", "scripts/verify_weekly_deploy.js", "--sync-downloads", "--check-vercel", "--expect-current-week"],
            env,
        )

    send_command = ["python3", "scripts/send_weekly_summary_email.py", "--require-recipients"]
    if args.preview_only:
        send_command.append("--preview-only")
    if args.recipients:
        send_command.extend(["--recipients", args.recipients])
    send_result = run_checked(send_command, env)

    output = {
        "ok": True,
        "config_path": str(config_path),
        "used_keychain_service": args.keychain_service,
        "verify_stdout": verify_result.stdout.strip() if verify_result else None,
        "send_stdout": send_result.stdout.strip(),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        payload = {
            "ok": False,
            "command": exc.cmd,
            "returncode": exc.returncode,
            "stdout": (exc.stdout or "").strip(),
            "stderr": (exc.stderr or "").strip(),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(exc.returncode)
