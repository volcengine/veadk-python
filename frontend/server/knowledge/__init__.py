"""Studio AgentKit knowledge-library backend."""

from .gateways import (
    SdkAgentKitKnowledgeGateway,
    VikingKnowledgeBaseProvisioner,
    build_viking_document_gateway_factory,
)
from .routes import mount_knowledge_routes
from .service import KnowledgeIdentity, KnowledgeService
from .uploads import TosKnowledgeUploadStore

__all__ = [
    "KnowledgeIdentity",
    "KnowledgeService",
    "SdkAgentKitKnowledgeGateway",
    "TosKnowledgeUploadStore",
    "VikingKnowledgeBaseProvisioner",
    "build_viking_document_gateway_factory",
    "mount_knowledge_routes",
]
