from typing import Any, Dict, List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.core.permissions import Permission
from app.modules.auth.dependencies import get_current_user, require_permission
from app.modules.automation.schemas import AutomationRuleCreate, AutomationRuleResponse, AutomationRuleUpdate
from app.modules.automation.service import AutomationService
from app.modules.users.models import User

router = APIRouter(prefix="/automation", tags=["Automation Workflows"])


@router.get("/rules", response_model=List[AutomationRuleResponse])
async def list_automation_rules(
    current_user: User = Depends(require_permission(Permission.AUTOMATION_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all automation workflow rules."""
    service = AutomationService(db, current_user.organization_id)
    rules = await service.list_rules()
    return [AutomationRuleResponse.model_validate(r) for r in rules]


@router.post("/rules", response_model=AutomationRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_automation_rule(
    req: AutomationRuleCreate,
    current_user: User = Depends(require_permission(Permission.AUTOMATION_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new automation rule with actions."""
    service = AutomationService(db, current_user.organization_id)
    rule = await service.create_rule(req)
    return AutomationRuleResponse.model_validate(rule)


@router.patch("/rules/{rule_id}", response_model=AutomationRuleResponse)
async def update_automation_rule(
    rule_id: str,
    req: AutomationRuleUpdate,
    current_user: User = Depends(require_permission(Permission.AUTOMATION_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Update or toggle an automation rule."""
    service = AutomationService(db, current_user.organization_id)
    rule = await service.update_rule(rule_id, req)
    return AutomationRuleResponse.model_validate(rule)

@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation_rule(
    rule_id: str,
    current_user: User = Depends(require_permission(Permission.AUTOMATION_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Delete an automation rule."""
    service = AutomationService(db, current_user.organization_id)
    await service.delete_rule(rule_id)


@router.post("/test-trigger")
async def test_trigger_event(
    event_trigger: str,
    payload: Dict[str, Any],
    current_user: User = Depends(require_permission(Permission.AUTOMATION_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Simulate a CRM event trigger to test active automation workflows."""
    service = AutomationService(db, current_user.organization_id)
    executed = await service.trigger_event(event_trigger, payload)
    return {
        "success": True,
        "event_trigger": event_trigger,
        "executed_actions": executed,
    }
