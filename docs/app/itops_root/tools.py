from typing import Dict, Any, Optional

def create_ticket(type: str, title: str, severity: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """创建工单（示例桩）。生产中调用企业工单系统 API，并返回工单链接。"""
    ticket_id = f"TCK-{severity.upper()}-0001"
    return {"id": ticket_id, "url": f"https://ticket.example.com/{ticket_id}", "title": title, "type": type, "severity": severity, "meta": meta or {}}

def query_cmdb(asset_id: Optional[str] = None, ip: Optional[str] = None) -> Dict[str, Any]:
    """CMDB 查询（示例桩）。生产中调用 CMDB API。"""
    return {"asset_id": asset_id or "host-001", "ip": ip or "10.0.0.1", "owner_dept": "network", "env": "prod"}
