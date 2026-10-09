# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Account/region network provisioning under the shared deployment/APIG lock."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import time
import uuid
from dataclasses import dataclass
from types import SimpleNamespace

from veadk.integrations.mpa.managed.database import DeploymentError
from veadk.integrations.mpa.managed.network_cloud import NetworkCloudError


def same_subnet_ids(first: object, second: object) -> bool:
    """Compare valid subnet selections without depending on provider ordering."""
    if not isinstance(first, list) or not isinstance(second, list):
        return False
    for selection in (first, second):
        if (
            not 1 <= len(selection) <= 5
            or any(not isinstance(sid, str) or not sid.strip() for sid in selection)
            or len(set(selection)) != len(selection)
        ):
            return False
    return set(first) == set(second)


def vpc_configuration_matches(actual: dict, requested: dict) -> bool:
    """Check supplied immutable network fields, treating subnets as members."""
    for key in ("VpcId", "SubnetIds", "EnableSharedInternetAccess"):
        if key not in requested:
            continue
        if key == "SubnetIds":
            if not same_subnet_ids(actual.get(key), requested[key]):
                return False
        elif actual.get(key) != requested[key]:
            return False
    return True


@dataclass(frozen=True)
class NetworkOptions:
    vpc_cidr: str = "172.20.0.0/16"
    subnet_prefix: int = 24
    zone_id: str = ""

    def validate(self):
        try:
            block = ipaddress.IPv4Network(self.vpc_cidr)
            # RFC 1918 includes the /8 range identified by leading octet 10.
            private = (
                block.prefixlen >= 8 and block.network_address.packed[0] == 10
            ) or any(
                block.subnet_of(ipaddress.IPv4Network(cidr))
                for cidr in (
                    "172.16.0.0/12",
                    "192.168.0.0/16",
                )
            )
            if not private or not block.prefixlen < self.subnet_prefix <= 29:
                raise ValueError()
        except ValueError:
            raise DeploymentError(
                "Network requires a private IPv4 VPC CIDR and a smaller subnet (prefix at most 29)"
            ) from None


def _available(subnet):
    return (
        str(subnet.get("status", "")).lower() == "available"
        and isinstance(subnet.get("available_ip_address_count"), int)
        and subnet["available_ip_address_count"] > 0
    )


class AccountNetworkProvisioner:
    def __init__(
        self,
        *,
        cloud,
        account,
        region,
        options=None,
        timeout: float = 300,
        interval: float = 3,
    ):
        self.cloud, self.account, self.region = cloud, account, region
        self.options = options or NetworkOptions()
        self.options.validate()
        self.timeout, self.interval = timeout, interval
        suffix = hashlib.sha256(f"{account}:{region}".encode()).hexdigest()[:20]
        self.name = f"mpa-network-{suffix}"
        self.marker = f"mpa-account-network-v1-{suffix}"
        self.legacy_marker = f"mpa-account-network:v1:{suffix}"

    async def _wait(self, fetch, resource_id, kind):
        deadline = time.monotonic() + self.timeout
        while True:
            row = await fetch(resource_id)
            if (
                row.get(f"{kind}_id") != resource_id
                or str(row.get("account_id")) != self.account
            ):
                raise DeploymentError(
                    f"{kind} identity/account differs from deployment account"
                )
            status = str(row.get("status", "")).lower()
            if status == "available":
                return row
            if status not in {"pending", "creating"}:
                raise DeploymentError(
                    f"Registered {kind} is unavailable; repair the resource before retrying"
                )
            if time.monotonic() >= deadline:
                raise DeploymentError(
                    f"{kind} is still creating; rerun the same deployment to resume"
                )
            await asyncio.sleep(self.interval)

    async def _create(self, entry, record, kind, request, matches):
        intent = kind + "_request"
        # Verify resources found by stable name. Never take over an arbitrary VPC.
        matches = [
            r for r in matches if r.get(f"{kind}_name") == request[f"{kind}_name"]
        ]
        if len(matches) > 1:
            raise DeploymentError(
                f"Multiple managed {kind} resources found; reconcile before continuing"
            )
        previous = {
            k: v for k, v in record.get(intent, {}).items() if k != "client_token"
        }
        if previous and previous != request:
            legacy = {**request, "description": self.legacy_marker}
            if previous != legacy:
                raise DeploymentError(
                    f"Unfinished {kind} creation has different inputs; resume its original configuration"
                )
            resource = record.get("vpc_id" if kind == "vpc" else "subnet_ids")
            if (
                record.get(kind + "_dispatched") is False
                and not resource
                and not matches
            ):
                # A changed body needs a fresh token, only after definite rejection.
                record[intent] = {**request, "client_token": str(uuid.uuid4())}
            elif matches:
                request = previous
            else:
                raise DeploymentError(
                    f"{kind} creation outcome unknown; retry discovery; no duplicate create issued"
                )
        if matches:
            row = matches[0]
            fields = ("description", "cidr_block") + (
                ("vpc_id", "zone_id") if kind == "subnet" else ()
            )
            if any(
                row.get(k) not in {self.marker, self.legacy_marker}
                if k == "description"
                else row.get(k) != request[k]
                for k in fields
            ):
                raise DeploymentError(
                    f"{kind} name exists without matching network ownership/configuration"
                )
            record.setdefault(intent, {**request, "client_token": str(uuid.uuid4())})
            return row[f"{kind}_id"]
        if record.get(kind + "_dispatched"):
            raise DeploymentError(
                f"{kind} creation outcome unknown; retry discovery; no duplicate create issued"
            )
        request = record.setdefault(
            intent, {**request, "client_token": str(uuid.uuid4())}
        )
        record[kind + "_dispatched"] = True
        await entry.save(record)
        try:
            return await getattr(self.cloud, "create_" + kind)(request)
        except NetworkCloudError as exc:
            # Only a definite API rejection permits another dispatch. Timeouts,
            # cancellations and unknown errors retain intent for discovery.
            if exc.code.startswith(
                ("Invalid", "Missing", "AccessDenied", "Unauthorized", "LimitExceeded")
            ):
                record[kind + "_dispatched"] = False
                await entry.save(record)
            raise

    def _free_cidr(self, vpc, subnets):
        try:
            block = ipaddress.IPv4Network(vpc["cidr_block"])
            occupied = [ipaddress.IPv4Network(s["cidr_block"]) for s in subnets]
            return next(
                str(n)
                for n in block.subnets(new_prefix=self.options.subnet_prefix)
                if not any(n.overlaps(other) for other in occupied)
            )
        except (ValueError, KeyError, StopIteration):
            raise DeploymentError(
                "No free subnet CIDR in VPC; choose a suitable subnet prefix or existing subnet"
            ) from None

    async def gateway_network(self, entry, network, available_zones):
        """Prepare standard APIG subnets while the caller holds the account lock."""
        if (
            not isinstance(available_zones, list)
            or any(
                not isinstance(zone, str)
                or not zone.startswith(self.region + "-")
                or not zone[len(self.region) + 1 :]
                for zone in available_zones
            )
            or len(set(available_zones)) != len(available_zones)
            or len(available_zones) < 2
        ):
            raise DeploymentError("APIG requires at least two valid available zones")
        config = dict(network["VpcConfiguration"])
        vpc_id = config["VpcId"]
        record = await entry.read()
        if record.get("vpc_id") != vpc_id:
            raise DeploymentError("APIG network differs from the registered VPC")
        vpc = await self._wait(self.cloud.vpc, vpc_id, "vpc")
        rows = await self.cloud.subnets(vpc_id)
        # DescribeSubnets may lag behind a ready GetSubnet. Reserve all known
        # primary CIDRs before allocating companions, even if listing is empty.
        initial = [
            await self._wait(self.cloud.subnet, sid, "subnet")
            for sid in config["SubnetIds"]
        ]
        if any(row.get("vpc_id") != vpc_id for row in initial):
            raise DeploymentError("APIG subnet is outside the registered VPC")
        known = {row["subnet_id"]: row for row in rows + initial}
        rows = list(known.values())
        intents = record.setdefault("gateway_subnet_intents", {})
        recovered = []

        async def companion(zone) -> dict:
            slot = intents.setdefault(zone, {})
            intent = slot.get("subnet_request")
            name = self.name + "-subnet-" + zone
            cidr = intent["cidr_block"] if intent else self._free_cidr(vpc, rows)
            try:
                block = ipaddress.IPv4Network(cidr)
                if (
                    block.prefixlen != self.options.subnet_prefix
                    or not block.subnet_of(ipaddress.IPv4Network(vpc["cidr_block"]))
                    or any(
                        block.overlaps(ipaddress.IPv4Network(row["cidr_block"]))
                        for row in rows
                        if row.get("subnet_name") != name
                    )
                ):
                    raise ValueError()
            except (ValueError, KeyError):
                raise DeploymentError(
                    "APIG companion subnet CIDR/configuration conflicts; reconcile before continuing"
                ) from None
            request = dict(
                vpc_id=vpc_id,
                zone_id=zone,
                cidr_block=cidr,
                subnet_name=name,
                description=self.marker,
            )

            async def save(pending):
                intents[zone] = pending
                await entry.save(record)

            subnet_id = await self._create(
                SimpleNamespace(save=save), slot, "subnet", request, rows
            )
            subnet = await self._wait(self.cloud.subnet, subnet_id, "subnet")
            if subnet.get("vpc_id") != vpc_id or not _available(subnet):
                raise DeploymentError(
                    "APIG companion subnet is unavailable/outside VPC"
                )
            if subnet.get("zone_id") != zone:
                raise DeploymentError("APIG companion subnet has a different zone")
            slot["subnet_ids"] = [subnet_id]
            await save(slot)
            return subnet

        # Resolve persisted intents first. Another subnet cannot hide an unknown
        # dispatch or cause a second create in a different zone on retry.
        for zone in sorted(intents):
            if zone not in available_zones:
                raise DeploymentError("Pending APIG subnet zone is no longer available")
            subnet = await companion(zone)
            recovered.append(subnet)
            rows = [r for r in rows if r["subnet_id"] != subnet["subnet_id"]] + [subnet]

        selected, zones = [], set()
        for row in initial + recovered + sorted(rows, key=lambda row: row["subnet_id"]):
            zone = row.get("zone_id")
            if zone not in available_zones or zone in zones or not _available(row):
                continue
            subnet = await self._wait(self.cloud.subnet, row["subnet_id"], "subnet")
            if (
                subnet.get("vpc_id") != vpc_id
                or subnet.get("zone_id") != zone
                or not _available(subnet)
            ):
                raise DeploymentError("APIG subnet identity/network changed")
            selected.append(subnet["subnet_id"])
            zones.add(zone)
            if len(selected) == 2:
                break
        for zone in sorted(available_zones):
            if len(selected) == 2:
                break
            if zone in zones:
                continue
            subnet = await companion(zone)
            selected.append(subnet["subnet_id"])
            zones.add(zone)
            rows.append(subnet)
        record["subnet_ids"] = selected
        await entry.save(record)
        return {**network, "VpcConfiguration": {**config, "SubnetIds": selected}}

    async def ensure(
        self, entry, requested=None, *, current=None, project_name="default"
    ):
        requested = dict(requested or {})
        config = dict(requested.get("VpcConfiguration") or {})
        if requested.get("EnablePublicNetwork") is False:
            raise DeploymentError("MPA requires public/private Runtime network access")
        if config.get("VpcId") and requested.get("EnablePrivateNetwork") is False:
            raise DeploymentError("MPA requires public/private Runtime network access")
        if config.get("SubnetIds") and not config.get("VpcId"):
            raise DeploymentError("SubnetIds require a VpcId")
        requested_subnets = config.get("SubnetIds")
        if current is not None:
            nets = {
                n["NetworkType"].lower(): n
                for n in current.get("NetworkConfigurations") or []
            }
            active = nets.get("private", {}).get("VpcConfiguration") or {}
            if (
                set(nets) != {"public", "private"}
                or not active.get("VpcId")
                or not active.get("SubnetIds")
            ):
                raise DeploymentError(
                    "Existing Runtime has no complete VPC network; create a new Runtime for migration"
                )
            if not vpc_configuration_matches(active, config):
                raise DeploymentError(
                    "Changing the Runtime VPC configuration requires a separate migration"
                )
            config = dict(active)
            if requested_subnets is not None:
                config["SubnetIds"] = list(requested_subnets)
        record = await entry.read()
        if (
            current is not None
            and requested_subnets is None
            and same_subnet_ids(config.get("SubnetIds"), record.get("subnet_ids"))
        ):
            # Keep the original creation order so provider permutations cannot
            # change the persisted request hash on same-agent recovery.
            config["SubnetIds"] = list(record["subnet_ids"])
        gateway = await entry.gateway()
        vpcs = {
            v
            for v in (config.get("VpcId"), record.get("vpc_id"), gateway.get("vpc_id"))
            if v
        }
        if len(vpcs) > 1:
            raise DeploymentError(
                "Requested VPC differs from the account network/shared APIG VPC"
            )
        # An explicit subnet overrides the account default only for this Runtime.
        subnet_ids = config.get("SubnetIds") or record.get("subnet_ids") or []
        vpc_id = next(iter(vpcs), "")
        if not vpc_id:
            request = dict(
                cidr_block=self.options.vpc_cidr,
                vpc_name=self.name,
                description=self.marker,
                project_name=project_name or "default",
            )
            vpc_id = await self._create(
                entry, record, "vpc", request, await self.cloud.find_vpcs(self.name)
            )
            record.update(vpc_id=vpc_id, managed_vpc=True)
            await entry.save(record)
        vpc = await self._wait(self.cloud.vpc, vpc_id, "vpc")
        if record.get("managed_vpc") and (
            vpc.get("description") not in {self.marker, self.legacy_marker}
            or vpc.get("cidr_block") != record["vpc_request"]["cidr_block"]
        ):
            raise DeploymentError(
                "Managed VPC ownership/CIDR changed; reconcile before deployment"
            )
        record["vpc_id"] = vpc_id
        # Persist selection before creating a subnet. APIG uses the same lock.
        await entry.save(record)
        if not subnet_ids:
            subnets = await self.cloud.subnets(vpc_id)
            intent = record.get("subnet_request")
            if not intent:
                candidates = sorted(
                    (
                        s
                        for s in subnets
                        if s.get("vpc_id") == vpc_id
                        and _available(s)
                        and (
                            not self.options.zone_id
                            or s.get("zone_id") == self.options.zone_id
                        )
                    ),
                    key=lambda s: s["subnet_id"],
                )
                if candidates:
                    subnet_ids = [candidates[0]["subnet_id"]]
            if not subnet_ids:
                zones = await self.cloud.zones()
                zone = self.options.zone_id or (intent or {}).get("zone_id") or zones[0]
                if zone not in zones:
                    raise DeploymentError(
                        "Deployment network zone is not available in this region"
                    )
                if intent:
                    cidr = intent["cidr_block"]
                    if (
                        ipaddress.IPv4Network(cidr).prefixlen
                        != self.options.subnet_prefix
                    ):
                        raise DeploymentError(
                            "Unfinished subnet creation has different prefix; resume its original configuration"
                        )
                else:
                    cidr = self._free_cidr(vpc, subnets)
                request = dict(
                    vpc_id=vpc_id,
                    zone_id=zone,
                    cidr_block=cidr,
                    subnet_name=self.name + "-subnet",
                    description=self.marker,
                )
                subnet_id = await self._create(
                    entry, record, "subnet", request, subnets
                )
                subnet_ids = [subnet_id]
                record.update(subnet_ids=subnet_ids, managed_subnet=True)
                await entry.save(record)
        if (
            not isinstance(subnet_ids, list)
            or not 1 <= len(subnet_ids) <= 5
            or len(set(subnet_ids)) != len(subnet_ids)
        ):
            raise DeploymentError("Specify 1 to 5 distinct subnet IDs")
        zones = set()
        for subnet_id in subnet_ids:
            subnet = await self._wait(self.cloud.subnet, subnet_id, "subnet")
            if subnet.get("vpc_id") != vpc_id or not _available(subnet):
                raise DeploymentError(
                    "Subnet is outside the selected VPC or has no available IP addresses"
                )
            zone = subnet.get("zone_id", "")
            if not zone.startswith(self.region + "-") or zone in zones:
                raise DeploymentError(
                    "Subnets must be in this region and in distinct zones"
                )
            zones.add(zone)
        record.setdefault("subnet_ids", subnet_ids)
        record["state"] = "ready"
        await entry.save(record)
        return {
            "EnablePublicNetwork": True,
            "EnablePrivateNetwork": True,
            "VpcConfiguration": {
                "VpcId": vpc_id,
                "SubnetIds": subnet_ids,
                "EnableSharedInternetAccess": config.get(
                    "EnableSharedInternetAccess", True
                ),
            },
        }
