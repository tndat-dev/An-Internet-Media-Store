#!/usr/bin/env python3
"""Promote verified GHCR digests into the AIMS Helm values file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ruamel.yaml import YAML


def load_digest(directory: Path, component: str) -> dict[str, str]:
    path = directory / f"digest-{component}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    repository = value.get("repository", "")
    digest = value.get("digest", "")
    if not repository.startswith("ghcr.io/") or not digest.startswith("sha256:"):
        raise ValueError(f"Invalid immutable image metadata in {path}")
    return {"repository": repository, "tag": digest, "pullPolicy": "IfNotPresent"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--values", required=True, type=Path)
    parser.add_argument("--digests", required=True, type=Path)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 1000
    with args.values.open(encoding="utf-8") as stream:
        values = yaml.load(stream)

    values["backendImage"] = load_digest(args.digests, "backend")
    values["sourceRevision"] = args.source_revision
    values["frontend"]["image"] = load_digest(args.digests, "frontend")
    # Registry images are pullable from every worker; the lab-only selector is
    # no longer required after the first successful promotion.
    values["frontend"]["nodeSelector"] = {}

    services = {item["name"]: item for item in values["services"]}
    notification = services["notification-service"]
    notification["image"] = load_digest(args.digests, "notification-service")
    notification["sourceRevision"] = args.source_revision

    inventory = services["inventory-service"]
    inventory["image"] = load_digest(args.digests, "inventory-service")
    inventory["sourceRevision"] = args.source_revision

    with args.values.open("w", encoding="utf-8") as stream:
        yaml.dump(values, stream)


if __name__ == "__main__":
    main()
