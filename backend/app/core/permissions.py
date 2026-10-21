from enum import Enum
from typing import Callable, List, Set
from fastapi import Depends
from app.core.exceptions import ForbiddenException


class RoleEnum(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    MEMBER = "MEMBER"


class Permission(str, Enum):
    # Leads
    LEADS_READ = "leads:read"
    LEADS_CREATE = "leads:create"
    LEADS_UPDATE = "leads:update"
    LEADS_DELETE = "leads:delete"

    # Contacts & Companies
    CONTACTS_READ = "contacts:read"
    CONTACTS_CREATE = "contacts:create"
    CONTACTS_UPDATE = "contacts:update"
    CONTACTS_DELETE = "contacts:delete"
    COMPANIES_READ = "companies:read"
    COMPANIES_CREATE = "companies:create"
    COMPANIES_UPDATE = "companies:update"
    COMPANIES_DELETE = "companies:delete"

    # Deals & Pipelines
    DEALS_READ = "deals:read"
    DEALS_CREATE = "deals:create"
    DEALS_UPDATE = "deals:update"
    DEALS_DELETE = "deals:delete"
    PIPELINES_MANAGE = "pipelines:manage"

    # Tasks & Activities
    TASKS_READ = "tasks:read"
    TASKS_CREATE = "tasks:create"
    TASKS_UPDATE = "tasks:update"
    TASKS_DELETE = "tasks:delete"
    ACTIVITIES_READ = "activities:read"
    ACTIVITIES_CREATE = "activities:create"
    ACTIVITIES_UPDATE = "activities:update"
    ACTIVITIES_DELETE = "activities:delete"
    CALENDAR_READ = "calendar:read"
    CALENDAR_CREATE = "calendar:create"
    CALENDAR_UPDATE = "calendar:update"
    CALENDAR_DELETE = "calendar:delete"

    # Automations & Reports
    AUTOMATION_READ = "automation:read"
    AUTOMATION_MANAGE = "automation:manage"
    REPORTS_READ = "reports:read"

    # AI Intelligence
    AI_USE = "ai:use"
    AI_MANAGE = "ai:manage"

    # Workspace & Team Admin
    TEAM_READ = "team:read"
    TEAM_MANAGE = "team:manage"
    SETTINGS_MANAGE = "settings:manage"
    IMPORTS_MANAGE = "imports:manage"


# Role to Permissions matrix
ROLE_PERMISSIONS: dict[RoleEnum, Set[Permission]] = {
    RoleEnum.OWNER: set(Permission),  # Full permissions
    RoleEnum.ADMIN: {
        p for p in Permission if p not in {Permission.SETTINGS_MANAGE}  # everything except workspace root destruction
    } | {Permission.SETTINGS_MANAGE},
    RoleEnum.MANAGER: {
        Permission.LEADS_READ,
        Permission.LEADS_CREATE,
        Permission.LEADS_UPDATE,
        Permission.LEADS_DELETE,
        Permission.CONTACTS_READ,
        Permission.CONTACTS_CREATE,
        Permission.CONTACTS_UPDATE,
        Permission.CONTACTS_DELETE,
        Permission.COMPANIES_READ,
        Permission.COMPANIES_CREATE,
        Permission.COMPANIES_UPDATE,
        Permission.COMPANIES_DELETE,
        Permission.DEALS_READ,
        Permission.DEALS_CREATE,
        Permission.DEALS_UPDATE,
        Permission.DEALS_DELETE,
        Permission.PIPELINES_MANAGE,
        Permission.TASKS_READ,
        Permission.TASKS_CREATE,
        Permission.TASKS_UPDATE,
        Permission.TASKS_DELETE,
        Permission.ACTIVITIES_READ,
        Permission.ACTIVITIES_CREATE,
        Permission.ACTIVITIES_UPDATE,
        Permission.ACTIVITIES_DELETE,
        Permission.CALENDAR_READ,
        Permission.CALENDAR_CREATE,
        Permission.CALENDAR_UPDATE,
        Permission.CALENDAR_DELETE,
        Permission.AUTOMATION_READ,
        Permission.AUTOMATION_MANAGE,
        Permission.REPORTS_READ,
        Permission.AI_USE,
        Permission.TEAM_READ,
        Permission.IMPORTS_MANAGE,
    },
    RoleEnum.MEMBER: {
        Permission.LEADS_READ,
        Permission.LEADS_CREATE,
        Permission.LEADS_UPDATE,
        Permission.CONTACTS_READ,
        Permission.CONTACTS_CREATE,
        Permission.CONTACTS_UPDATE,
        Permission.COMPANIES_READ,
        Permission.COMPANIES_CREATE,
        Permission.COMPANIES_UPDATE,
        Permission.DEALS_READ,
        Permission.DEALS_CREATE,
        Permission.DEALS_UPDATE,
        Permission.TASKS_READ,
        Permission.TASKS_CREATE,
        Permission.TASKS_UPDATE,
        Permission.ACTIVITIES_READ,
        Permission.ACTIVITIES_CREATE,
        Permission.ACTIVITIES_UPDATE,
        Permission.CALENDAR_READ,
        Permission.CALENDAR_CREATE,
        Permission.CALENDAR_UPDATE,
        Permission.REPORTS_READ,
        Permission.AI_USE,
    },
}


def has_permission(role: str, permission: Permission) -> bool:
    """Check if a given role possesses a specific permission."""
    try:
        role_enum = RoleEnum(role.upper())
        allowed = ROLE_PERMISSIONS.get(role_enum, set())
        return permission in allowed
    except ValueError:
        return False
