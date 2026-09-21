"""In-memory cloud and durable network entry for deployment recovery tests."""

import copy


class NetworkEntry:
    def __init__(self):
        self.row = {}
        self.gateway_row = {}
        self.saved = []

    async def read(self):
        return copy.deepcopy(self.row)

    async def save(self, row):
        self.row = copy.deepcopy(row)
        self.saved.append(copy.deepcopy(row))

    async def gateway(self):
        return copy.deepcopy(self.gateway_row)


class NetworkCloud:
    def __init__(self, *, existing=False):
        self.vpcs, self.subnet_rows = {}, {}
        self.calls = []
        self.lose = ""
        self.hide = False
        self.zone_ids = ["cn-beijing-a", "cn-beijing-b"]
        if existing:
            self.vpcs["vpc-one"] = self.vpc_row("vpc-one")
            self.subnet_rows["subnet-one"] = self.subnet_row("subnet-one", "vpc-one")

    def vpc_row(self, vid):
        return dict(
            vpc_id=vid,
            account_id="account",
            status="Available",
            cidr_block="172.20.0.0/16",
        )

    def subnet_row(self, sid, vid):
        return dict(
            subnet_id=sid,
            vpc_id=vid,
            account_id="account",
            status="Available",
            cidr_block="172.20.0.0/24",
            zone_id="cn-beijing-a",
            available_ip_address_count=250,
        )

    async def zones(self):
        return self.zone_ids.copy()

    async def vpc(self, vid):
        return copy.deepcopy(self.vpcs[vid])

    async def subnet(self, sid):
        return copy.deepcopy(self.subnet_rows[sid])

    async def find_vpcs(self, name):
        return (
            []
            if self.hide
            else copy.deepcopy(
                [v for v in self.vpcs.values() if v.get("vpc_name") == name]
            )
        )

    async def subnets(self, vid):
        return (
            []
            if self.hide
            else copy.deepcopy(
                [s for s in self.subnet_rows.values() if s["vpc_id"] == vid]
            )
        )

    async def create_vpc(self, request):
        self.calls.append(("vpc", copy.deepcopy(request)))
        vid = "vpc-auto"
        self.vpcs[vid] = {**self.vpc_row(vid), **request}
        if self.lose == "vpc":
            self.lose = ""
            raise TimeoutError("lost VPC response")
        return vid

    async def create_subnet(self, request):
        self.calls.append(("subnet", copy.deepcopy(request)))
        sid = "subnet-auto"
        self.subnet_rows[sid] = {**self.subnet_row(sid, request["vpc_id"]), **request}
        if self.lose == "subnet":
            self.lose = ""
            raise TimeoutError("lost subnet response")
        return sid
