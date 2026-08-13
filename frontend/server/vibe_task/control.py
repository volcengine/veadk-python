# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
# Licensed under the Apache License, Version 2.0 (the "License");

from __future__ import annotations

import hashlib
import json
import shlex
from typing import Literal

from pydantic import Field, field_validator

from .models import IntentSummary, VibeModel

REMOTE_TASK_ROOT = "/home/gem/.vibe/task"
REMOTE_COMMAND_INBOX = f"{REMOTE_TASK_ROOT}/commands/inbox"
REMOTE_COMMAND_PROCESSED = f"{REMOTE_TASK_ROOT}/commands/processed"
REMOTE_CONTROL_WORKER_PATH = f"{REMOTE_TASK_ROOT}/control-worker.py"
REMOTE_SECRETS_ROOT = f"{REMOTE_TASK_ROOT}/secrets"


class _ControlCommand(VibeModel):
    command_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    task_id: str = Field(pattern=r"^vt-[0-9a-f]{12}-[0-9a-f]{24}$")
    timestamp: str = Field(min_length=1, max_length=80)


class IntentUpdateCommand(_ControlCommand):
    command_type: Literal["intent.update"]
    expected_revision: int = Field(ge=0)
    summary: IntentSummary


class CredentialsMarkerCommand(_ControlCommand):
    command_type: Literal["credentials.marker"]
    secret_relative_path: str

    @field_validator("secret_relative_path")
    @classmethod
    def validate_secret_path(cls, value: str) -> str:
        parts = value.split("/")
        if not value or value.startswith("/") or any(part in ("", ".", "..") for part in parts):
            raise ValueError("secret path must be a normalized relative path")
        if parts[0] != "secrets":
            raise ValueError("secret path must be below secrets")
        return value


class StopCommand(_ControlCommand):
    command_type: Literal["task.stop"]
    reason: str = Field(default="", max_length=500)


ControlCommand = IntentUpdateCommand | CredentialsMarkerCommand | StopCommand


# This is the canonical, dependency-free sandbox implementation. It is installed once by
# bootstrap; subsequent invocations receive only a command JSON file path.
CONTROL_WORKER_SOURCE = r'''from __future__ import annotations
import fcntl, hashlib, json, os, stat, sys, tempfile
from pathlib import Path

ROOT = os.environ.get("VIBE_TASK_ROOT", "/home/gem/.vibe/task")
REQUEST = os.path.join(ROOT, "request.json")
STATUS = os.path.join(ROOT, "status.json")
EVENTS = os.path.join(ROOT, "events.jsonl")
LOCK = os.path.join(ROOT, "state.lock")
INTENT = os.path.join(ROOT, "intent-summary.json")
PROCESSED = os.path.join(ROOT, "commands/processed")
SECRETS = os.path.join(ROOT, "secrets")
GENESIS = "0" * 64
TERMINAL = {"completed", "partial", "blocked", "failed", "cancelled", "expired"}
STATES = {"provisioning", "ready", "running"} | TERMINAL
STAGES = {"provisioning", "understanding", "building", "local_validation", "cloud_build", "runtime_validation", "delivering", "cleanup", "done"}

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()
def event_digest(value):
    names = {"schemaVersion":"schema_version", "taskId":"task_id", "previousHash":"previous_hash", "eventType":"event_type"}
    projection_names = {"credentialsConfigured":"credentials_configured", "intentRevision":"intent_revision", "sandboxSessionId":"sandbox_session_id", "validationRuntimeId":"validation_runtime_id", "validationRuntimeStatus":"validation_runtime_status"}
    normalized = {names.get(key, key): item for key, item in value.items()}
    projection = {key: None for key in ("state", "stage", "attempt", "credentials_configured", "intent_revision", "sandbox_session_id", "validation_runtime_id", "validation_runtime_status", "artifact", "warnings", "error")}
    projection.update({projection_names.get(key, key): item for key, item in value["projection"].items()})
    normalized["projection"] = projection
    return digest(normalized)
def load(path):
    with open(path, encoding="utf-8") as stream: return json.load(stream)
def atomic(path, value, mode=0o600):
    directory = os.path.dirname(path); os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=directory)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(value); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        dfd = os.open(directory, os.O_RDONLY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    except BaseException:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise

def exact_keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or not set(value) <= set(required) | set(optional):
        raise ValueError("invalid object schema")
def validate_request(value):
    exact_keys(value, {"schemaVersion", "taskId", "requestId", "goal", "displayName"})
    if value["schemaVersion"] != 1 or not isinstance(value["taskId"], str) or not isinstance(value["goal"], str): raise ValueError("invalid request")
def validate_status(value, task):
    required = {"taskId", "displayName", "goal", "state", "stage", "createdAt", "expiresAt", "attempt", "lastSequence", "credentialsConfigured", "intentRevision", "sandboxSessionId", "validationRuntimeId", "validationRuntimeStatus", "artifact", "warnings", "error"}
    exact_keys(value, required)
    if value["taskId"] != task or value["state"] not in STATES or value["stage"] not in STAGES: raise ValueError("invalid status")
    if not isinstance(value["lastSequence"], int) or not isinstance(value["intentRevision"], int): raise ValueError("invalid status counters")
def validate_intent(value):
    required = {"revision", "goal", "confirmedRequirements", "constraints", "assumptions", "openQuestions", "successCriteria", "architectureSummary", "currentStatus", "evidence", "updatedAt"}
    exact_keys(value, required)
    if not isinstance(value["revision"], int) or value["revision"] < 0: raise ValueError("invalid intent")
def replay(text, task):
    previous = GENESIS; records = []
    lines = text.splitlines()
    if text and not text.endswith("\n"): raise ValueError("truncated event log")
    for sequence, line in enumerate(lines, 1):
        if not line: raise ValueError("blank event record")
        record = json.loads(line)
        required = {"schemaVersion", "taskId", "sequence", "previousHash", "eventHash", "eventType", "stage", "timestamp", "payload", "projection"}
        exact_keys(record, required)
        supplied = record.pop("eventHash")
        valid_hash = event_digest(record)
        record["eventHash"] = supplied
        if record["schemaVersion"] != 1 or record["taskId"] != task or record["sequence"] != sequence or record["previousHash"] != previous or supplied != valid_hash or record["stage"] not in STAGES: raise ValueError("invalid event chain")
        if not isinstance(record["payload"], dict) or not isinstance(record["projection"], dict): raise ValueError("invalid event body")
        previous = supplied; records.append(record)
    return records, previous
def project(status, records):
    result = dict(status)
    projection_keys = {"state", "stage", "attempt", "credentialsConfigured", "intentRevision", "sandboxSessionId", "validationRuntimeId", "validationRuntimeStatus", "artifact", "warnings", "error"}
    for record in records:
        if not set(record["projection"]) <= projection_keys: raise ValueError("invalid projection")
        result.update({key: value for key, value in record["projection"].items() if value is not None})
        result["lastSequence"] = record["sequence"]
    validate_status(result, status["taskId"])
    return result
def append_event(records, previous, command, event_type, stage, payload, projection):
    body = {"schemaVersion": 1, "taskId": command["taskId"], "sequence": len(records)+1, "previousHash": previous, "eventType": event_type, "stage": stage, "timestamp": command["timestamp"], "payload": payload, "projection": projection}
    body["eventHash"] = event_digest(body); records.append(body)
    return body["eventHash"]
def validate_command(command):
    common = {"commandId", "taskId", "commandType", "timestamp"}
    kind = command.get("commandType") if isinstance(command, dict) else None
    extras = {"intent.update": {"expectedRevision", "summary"}, "credentials.marker": {"secretRelativePath"}, "task.stop": set()}.get(kind)
    optional = {"reason"} if kind == "task.stop" else set()
    if extras is None: raise ValueError("unknown command")
    exact_keys(command, common | extras, optional)
    if not isinstance(command["commandId"], str) or len(command["commandId"]) != 32 or any(c not in "0123456789abcdef" for c in command["commandId"]): raise ValueError("invalid command id")

def scrub_secrets():
    try: root_info = os.lstat(SECRETS)
    except FileNotFoundError: return
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode): raise ValueError("secrets root must be a real directory")
    for directory, dirs, files in os.walk(SECRETS, topdown=False, followlinks=False):
        for name in files + dirs:
            path = os.path.join(directory, name)
            try:
                if os.path.islink(path) or not os.path.isdir(path): os.unlink(path)
                else: os.rmdir(path)
            except FileNotFoundError: pass

def main(path):
    command = load(path); validate_command(command)
    with open(LOCK, "a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        request = load(REQUEST); validate_request(request)
        if command["taskId"] != request["taskId"]: raise ValueError("command task mismatch")
        persisted = load(STATUS); validate_status(persisted, request["taskId"])
        with open(EVENTS, encoding="utf-8") as stream: records, previous = replay(stream.read(), request["taskId"])
        base = dict(persisted); base.update({"state": "provisioning", "stage": "provisioning", "attempt": 0, "lastSequence": 0, "credentialsConfigured": False, "intentRevision": 0, "validationRuntimeId": "", "validationRuntimeStatus": "", "artifact": None, "warnings": [], "error": ""})
        status = project(base, records)
        intent = load(INTENT); validate_intent(intent)
        if intent["revision"] != status["intentRevision"]: raise ValueError("intent projection mismatch")
        processed = os.path.join(PROCESSED, command["commandId"] + ".json")
        command_hash = digest(command)
        committed = next((item for item in records if item.get("payload", {}).get("commandId") == command["commandId"]), None)
        if committed is not None:
            if committed.get("payload", {}).get("commandHash") != command_hash: raise ValueError("command id collision")
            summary = committed.get("payload", {}).get("summary")
            if summary is not None:
                validate_intent(summary); intent = summary
            atomic(STATUS, json.dumps(status, separators=(",", ":")) + "\n")
            atomic(INTENT, json.dumps(intent, separators=(",", ":")) + "\n")
            atomic(processed, json.dumps({"commandHash": command_hash}, separators=(",", ":")) + "\n")
            return
        if os.path.lexists(processed):
            record = load(processed)
            if record != {"commandHash": command_hash}: raise ValueError("command id collision")
            raise ValueError("processed command has no committed event")
        if status["state"] in TERMINAL: raise ValueError("task is terminal")
        kind = command["commandType"]
        if kind == "intent.update":
            if command["expectedRevision"] != status["intentRevision"]: raise ValueError("intent revision conflict")
            summary = command["summary"]; validate_intent(summary)
            if summary["revision"] != command["expectedRevision"] + 1: raise ValueError("summary revision must advance once")
            intent = summary
            append_event(records, previous, command, "vibe.intent.updated", status["stage"], {"commandId": command["commandId"], "commandHash": command_hash, "revision": summary["revision"], "summary": summary}, {"intentRevision": summary["revision"]})
        elif kind == "credentials.marker":
            relative = command["secretRelativePath"]
            if not isinstance(relative, str) or relative.startswith("/") or relative.split("/")[0] != "secrets" or any(x in ("", ".", "..") for x in relative.split("/")): raise ValueError("invalid secret path")
            secret = os.path.join(ROOT, relative)
            parent_real = os.path.realpath(os.path.dirname(secret))
            if os.path.commonpath((os.path.realpath(SECRETS), parent_real)) != os.path.realpath(SECRETS): raise ValueError("secret escapes root")
            info = os.lstat(secret)
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600: raise ValueError("secret must be a regular 0600 file")
            append_event(records, previous, command, "credentials.configured", status["stage"], {"commandId": command["commandId"], "commandHash": command_hash}, {"credentialsConfigured": True})
        else:
            scrub_secrets()
            append_event(records, previous, command, "task.cancelled", "done", {"commandId": command["commandId"], "commandHash": command_hash, "reason": command.get("reason", "")}, {"state": "cancelled", "stage": "done", "credentialsConfigured": False})
        status = project(base, records)
        event_text = "".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n" for item in records)
        atomic(EVENTS, event_text)
        atomic(STATUS, json.dumps(status, ensure_ascii=False, separators=(",", ":")) + "\n")
        atomic(INTENT, json.dumps(intent, ensure_ascii=False, separators=(",", ":")) + "\n")
        atomic(processed, json.dumps({"commandHash": command_hash}, separators=(",", ":")) + "\n")
if __name__ == "__main__":
    if len(sys.argv) != 2: raise SystemExit("usage: control-worker.py COMMAND_JSON_PATH")
    main(sys.argv[1])
'''


def build_control_command(
    command: ControlCommand,
    *,
    inbox: str = REMOTE_COMMAND_INBOX,
    worker_path: str = REMOTE_CONTROL_WORKER_PATH,
    task_root: str = REMOTE_TASK_ROOT,
) -> str:
    """Build an invocation that stages one command and passes only its path to the worker."""
    if not isinstance(command, (IntentUpdateCommand, CredentialsMarkerCommand, StopCommand)):
        raise TypeError("command must be a control command")
    path = f"{inbox}/{command.command_id}.json"
    value = command.model_dump_json(by_alias=True) + "\n"
    source = (
        "import os,tempfile\n"
        f"path={path!r}; value={value!r}\n"
        "os.makedirs(os.path.dirname(path),mode=0o700,exist_ok=True)\n"
        "fd,tmp=tempfile.mkstemp(dir=os.path.dirname(path))\n"
        "with os.fdopen(fd,'w',encoding='utf-8') as f: f.write(value); f.flush(); os.fsync(f.fileno())\n"
        "os.replace(tmp,path)\n"
        f"os.environ['VIBE_TASK_ROOT']={task_root!r}\n"
        f"os.execv('/usr/bin/python3',['/usr/bin/python3',{worker_path!r},path])\n"
    )
    return f"python3 -c {shlex.quote(source)}"


def control_worker_sha256() -> str:
    return hashlib.sha256(CONTROL_WORKER_SOURCE.encode()).hexdigest()
