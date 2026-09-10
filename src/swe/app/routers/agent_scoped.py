# -*- coding: utf-8 -*-
"""Agent-scoped router that wraps existing routers under /agents/{agentId}/

This provides agent isolation by injecting agentId into request.state,
allowing downstream APIs to access the correct agent context.

Note: For tenant-scoped deployments, tenant identity is resolved first
before agent resolution. The agent namespace is per-tenant.
"""

import logging
import time

from fastapi import APIRouter, Request
from fastapi.routing import APIRoute
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.responses import Response

from ..middleware.provider_models_timing import (
    is_provider_models_list_request,
    log_provider_models_middleware_before_next,
    log_provider_models_middleware_done,
    log_provider_models_middleware_error,
)

logger = logging.getLogger(__name__)


class AgentContextMiddleware(BaseHTTPMiddleware):
    """Middleware to inject agentId into request.state.

    Note: This middleware assumes tenant identity has already been
    resolved by TenantIdentityMiddleware and TenantWorkspaceMiddleware.
    Agent resolution happens within the tenant context.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Extract agentId from path/header and inject into context.

        Tenant context (if set by prior middleware) takes precedence
        for agent namespace resolution.
        """
        from ..agent_context import set_current_agent_id
        from ...config.context import get_current_tenant_id

        is_timing = is_provider_models_list_request(request)
        started_at = time.perf_counter()
        before_next_at = None
        agent_id = None

        # Log tenant context if available
        tenant_id = get_current_tenant_id()
        if tenant_id:
            logger.debug(f"AgentContextMiddleware: tenant_id={tenant_id}")

        # Priority 1: Extract agentId from path: /api/agents/{agentId}/...
        path_parts = request.url.path.split("/")
        if len(path_parts) >= 4 and path_parts[1] == "api":
            if path_parts[2] == "agents":
                agent_id = path_parts[3]
                request.state.agent_id = agent_id
                logger.debug(
                    f"AgentContextMiddleware: agent_id={agent_id} "
                    f"from path={request.url.path}",
                )

        # Priority 2: Check X-Agent-Id header
        if not agent_id:
            agent_id = request.headers.get("X-Agent-Id")

        # Set agent_id in context variable for use by runners
        if agent_id:
            set_current_agent_id(agent_id)

        try:
            if is_timing:
                before_next_at = log_provider_models_middleware_before_next(
                    logger,
                    "AgentContextMiddleware",
                    request,
                    started_at,
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                )
            response = await call_next(request)
            if is_timing and before_next_at is not None:
                log_provider_models_middleware_done(
                    logger,
                    "AgentContextMiddleware",
                    request,
                    started_at,
                    before_next_at,
                    response,
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                )
            return response
        except Exception:
            if is_timing:
                log_provider_models_middleware_error(
                    logger,
                    "AgentContextMiddleware",
                    request,
                    started_at,
                    before_next_at,
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                )
            raise


def create_agent_scoped_router() -> APIRouter:
    """Create router that wraps all existing routers under /{agentId}/

    Returns:
        APIRouter with all sub-routers mounted under /{agentId}/

    Note: These routes are within a tenant context when tenant
    middleware is applied. Agent namespace is per-tenant.
    """
    from .agent import router as agent_router
    from .approvals import router as approvals_router
    from .skills import router as skills_router
    from .tools import router as tools_router
    from .config import router as config_router
    from .mcp import router as mcp_router
    from .workspace import router as workspace_router
    from ..crons.api import router as cron_router
    from ..runner.api import router as chats_router
    from .console import router as console_router
    from ..wplus_sop.router import router as wplus_sop_router
    from .subagents import router as subagents_router
    from .experts import router as experts_router

    # Create parent router with agentId parameter
    router = APIRouter(prefix="/agents/{agentId}", tags=["agent-scoped"])

    scoped_agent_router = APIRouter()
    scoped_agent_router.include_router(agent_router)
    scoped_agent_router.routes = [
        route
        for route in scoped_agent_router.routes
        if not (isinstance(route, APIRoute) and route.path == "/agent/init")
    ]

    # Include all agent-specific sub-routers (they keep their own prefixes)
    # /agents/{agentId}/agent/* -> agent_router
    # /agents/{agentId}/chats/* -> chats_router
    # /agents/{agentId}/config/* -> config_router (channels, heartbeat)
    # /agents/{agentId}/cron/* -> cron_router
    # /agents/{agentId}/mcp/* -> mcp_router
    # /agents/{agentId}/skills/* -> skills_router
    # /agents/{agentId}/tools/* -> tools_router
    # /agents/{agentId}/workspace/* -> workspace_router
    router.include_router(scoped_agent_router)
    router.include_router(approvals_router)
    router.include_router(chats_router)
    router.include_router(config_router)
    router.include_router(cron_router)
    router.include_router(mcp_router)
    router.include_router(skills_router)
    router.include_router(tools_router)
    router.include_router(workspace_router)
    router.include_router(console_router)
    router.include_router(wplus_sop_router)
    router.include_router(subagents_router)
    router.include_router(experts_router)

    return router
