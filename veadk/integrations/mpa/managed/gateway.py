"""Create/reuse one managed message gateway per verified account and region."""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from veadk.integrations.mpa.managed.gateway_cloud import APIGClientError


class SharedGatewayError(RuntimeError):
    """Operator-facing error without credentials or provider response bodies."""


class SharedAPIGService:
    def __init__(
        self,
        *,
        registry: Any,
        cloud: Any,
        region: str,
        attempts: int = 60,
        interval: float = 5,
    ):
        if attempts < 1:
            raise ValueError("Gateway polling attempts must be positive")
        self.registry, self.cloud, self.region = registry, cloud, region
        self.attempts, self.interval = attempts, interval

    async def ensure(
        self, *, vpc_id: str, subnet_ids: list[str], adopt_id: str = ""
    ) -> dict:
        if not vpc_id or not subnet_ids or not all(subnet_ids):
            raise SharedGatewayError("Runtime VPC and subnet IDs are required")
        account_id = await self.cloud.account_id()
        suffix = hashlib.sha256(f"{account_id}:{self.region}".encode()).hexdigest()[:20]
        name = f"mpa-im-{suffix}"
        await self.registry.initialize()
        async with self.registry.lock(account_id, self.region) as entry:
            record = await entry.read()
            if record and record["vpc_id"] != vpc_id:
                raise SharedGatewayError(
                    "Account gateway uses another VPC; connect Runtime to the shared gateway network"
                )
            if adopt_id and record.get("gateway_id") not in (None, "", adopt_id):
                raise SharedGatewayError(
                    "Account already has a different shared gateway"
                )
            gateway_id = record.get("gateway_id") or adopt_id
            if not gateway_id:
                matches = await self.cloud.find_gateways(name)
                if len(matches) > 1:
                    raise SharedGatewayError(
                        "Multiple managed gateways found; reconcile before continuing"
                    )
                if matches:
                    gateway_id = matches[0]["Id"]
                elif record.get("create_requested"):
                    raise SharedGatewayError(
                        "Gateway creation outcome unknown; retry discovery or adopt the verified gateway ID; no duplicate create issued"
                    )
                else:
                    record = {"vpc_id": vpc_id, "name": name, "create_requested": True}
                    await entry.save(record)
                    # Persist intent before dispatch. A timeout/crash cannot
                    # cause a second CreateGateway on the next attempt.
                    try:
                        gateway_id = await self.cloud.create_gateway(
                            name, vpc_id, subnet_ids
                        )
                    except APIGClientError as exc:
                        if exc.code.startswith(
                            (
                                "Invalid",
                                "Missing",
                                "AccessDenied",
                                "Unauthorized",
                                "LimitExceeded",
                            )
                        ):
                            record["create_requested"] = False
                            await entry.save(record)
                        raise
                    record["gateway_id"] = gateway_id
                    await entry.save(record)
            gateway = await self.cloud.get_gateway(gateway_id)
            for attempt in range(self.attempts):
                if gateway.get("Region") != self.region or gateway.get("Type") not in {
                    "serverless",
                    "standard",
                }:
                    raise SharedGatewayError(
                        "Gateway region/type does not match the shared gateway configuration"
                    )
                if (gateway.get("NetworkSpec") or {}).get("VpcId") != vpc_id:
                    raise SharedGatewayError("Gateway VPC does not match Runtime VPC")
                record.update(gateway_id=gateway_id, vpc_id=vpc_id, name=name)
                await entry.save(record)
                status = str(gateway.get("Status") or "").lower()
                if status == "running":
                    network = (gateway.get("ResourceSpec") or {}).get(
                        "NetworkType"
                    ) or {}
                    if network.get("EnablePrivateNetwork") is False:
                        raise SharedGatewayError(
                            "Shared gateway private network is disabled"
                        )
                    break
                if status in {"failed", "deleting", "deleted"}:
                    raise SharedGatewayError(
                        "Shared gateway is unavailable; repair the existing resource"
                    )
                if attempt + 1 == self.attempts:
                    raise SharedGatewayError(
                        "Shared gateway is still creating; retry later"
                    )
                await asyncio.sleep(self.interval)
                gateway = await self.cloud.get_gateway(gateway_id)
            try:
                im = await self.cloud.get_im_gateway_service_status(
                    gateway_id=gateway_id
                )
            except APIGClientError as exc:
                if exc.code != "ResourceNotFound":
                    raise
                if record.get("im_create_requested"):
                    raise SharedGatewayError(
                        "IM Gateway creation outcome unknown; retry status lookup; no duplicate create issued"
                    ) from None
                record["im_create_requested"] = True
                await entry.save(record)
                try:
                    await self.cloud.create_im_gateway_service(gateway_id=gateway_id)
                except APIGClientError as exc:
                    if exc.code.startswith(
                        (
                            "Invalid",
                            "Missing",
                            "AccessDenied",
                            "Unauthorized",
                            "LimitExceeded",
                        )
                    ):
                        record["im_create_requested"] = False
                        await entry.save(record)
                    raise
                im = await self.cloud.wait_im_gateway_service_ready(
                    gateway_id=gateway_id
                )
            else:
                if getattr(im, "status", "") != "RUNNING":
                    im = await self.cloud.wait_im_gateway_service_ready(
                        gateway_id=gateway_id
                    )
            if not im.im_gateway_endpoint or not im.im_gateway_service_id:
                raise SharedGatewayError(
                    "IM Gateway returned incomplete service metadata"
                )
            record.update(
                im_gateway_endpoint=im.im_gateway_endpoint,
                im_gateway_service_id=im.im_gateway_service_id,
                state="ready",
            )
            await entry.save(record)
            return {**record, "account_id": account_id, "region": self.region}
