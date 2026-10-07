import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.core.database import AsyncSessionLocal, engine
from app.core.security import hash_password
from app.modules.activities.models import Activity, ActivityType
from app.modules.ai.models import AIInsight, InsightType
from app.modules.automation.models import AutomationAction, AutomationRule
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal, DealStatus
from app.modules.leads.models import Lead, LeadPriority, LeadStatus
from app.modules.notifications.models import Notification
from app.modules.organizations.models import Organization
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.tasks.models import Task, TaskPriority, TaskStatus, TaskType
from app.modules.users.models import User


async def seed_database():
    """Seed comprehensive realistic CRM business data."""
    async with AsyncSessionLocal() as session:
        # Check if already seeded
        existing_org = (
            await session.execute(
                select(Organization).where(Organization.slug == "nexus-dynamics")
            )
        ).scalar_one_or_none()

        if existing_org:
            print("Database already seeded with 'nexus-dynamics'. Skipping.")
            return

        print("Seeding NexusCRM database with realistic demo dataset...")
        now = datetime.now(timezone.utc)

        # 1. Create Organization
        org = Organization(
            name="Nexus Dynamics Corp",
            slug="nexus-dynamics",
            domain="nexusdynamics.io",
            plan="growth",
            is_active=True,
            settings={
                "currency": "USD",
                "timezone": "UTC",
                "lead_scoring_enabled": True,
                "fiscal_year_start": "January",
            },
        )
        session.add(org)
        await session.flush()

        # 2. Create Users
        owner_user = User(
            organization_id=org.id,
            email="ali@nexusdynamics.io",
            hashed_password=hash_password("password123"),
            first_name="Ali",
            last_name="Raza",
            role="OWNER",
            is_active=True,
            is_verified=True,
        )
        admin_user = User(
            organization_id=org.id,
            email="sarah@nexusdynamics.io",
            hashed_password=hash_password("password123"),
            first_name="Sarah",
            last_name="Jenkins",
            role="ADMIN",
            is_active=True,
            is_verified=True,
        )
        rep_user = User(
            organization_id=org.id,
            email="bilal@nexusdynamics.io",
            hashed_password=hash_password("password123"),
            first_name="Bilal",
            last_name="Tariq",
            role="MEMBER",
            is_active=True,
            is_verified=True,
        )
        session.add_all([owner_user, admin_user, rep_user])
        await session.flush()

        # 3. Create Default Sales Pipeline & Stages
        pipeline = Pipeline(
            organization_id=org.id,
            name="Enterprise Sales Pipeline",
            is_default=True,
        )
        session.add(pipeline)
        await session.flush()

        stages_data = [
            ("New", 1, 10, False, False),
            ("Contacted", 2, 20, False, False),
            ("Qualified", 3, 40, False, False),
            ("Interested", 4, 60, False, False),
            ("Proposal", 5, 75, False, False),
            ("Negotiation", 6, 90, False, False),
            ("Won", 7, 100, True, False),
            ("Lost", 8, 0, False, True),
        ]
        stages_dict = {}
        for name, order, prob, is_won, is_lost in stages_data:
            st = PipelineStage(
                organization_id=org.id,
                pipeline_id=pipeline.id,
                name=name,
                order=order,
                win_probability=prob,
                is_won=is_won,
                is_lost=is_lost,
            )
            session.add(st)
            stages_dict[name] = st
        await session.flush()

        # 4. Create Companies
        comp_apex = Company(
            organization_id=org.id,
            name="Apex Logistics Global",
            domain="apexlogistics.com",
            industry="Transportation & Logistics",
            size="51-200",
            phone="+1 (555) 234-5678",
            city="Chicago",
            country="USA",
        )
        comp_cloudscale = Company(
            organization_id=org.id,
            name="CloudScale Infrastructure",
            domain="cloudscale.io",
            industry="Cloud Computing",
            size="201-500",
            phone="+1 (555) 876-5432",
            city="Austin",
            country="USA",
        )
        comp_medtech = Company(
            organization_id=org.id,
            name="MedTech Systems",
            domain="medtechsystems.org",
            industry="Healthcare Software",
            size="11-50",
            phone="+1 (555) 987-1234",
            city="Boston",
            country="USA",
        )
        session.add_all([comp_apex, comp_cloudscale, comp_medtech])
        await session.flush()

        # 5. Create Contacts
        contact_ahmed = Contact(
            organization_id=org.id,
            company_id=comp_apex.id,
            first_name="Ahmed",
            last_name="Khan",
            email="ahmed.khan@apexlogistics.com",
            phone="+1 (555) 345-9876",
            title="VP of Operations",
            lead_source="Website Form",
        )
        contact_elena = Contact(
            organization_id=org.id,
            company_id=comp_cloudscale.id,
            first_name="Elena",
            last_name="Vance",
            email="elena.vance@cloudscale.io",
            phone="+1 (555) 456-7890",
            title="Director of Engineering",
            lead_source="Referral",
        )
        contact_marcus = Contact(
            organization_id=org.id,
            company_id=comp_medtech.id,
            first_name="Dr. Marcus",
            last_name="Chen",
            email="m.chen@medtechsystems.org",
            phone="+1 (555) 567-8901",
            title="Chief Information Officer",
            lead_source="Cold Outreach",
        )
        session.add_all([contact_ahmed, contact_elena, contact_marcus])
        await session.flush()

        # 6. Create Leads
        lead_ahmed = Lead(
            organization_id=org.id,
            contact_id=contact_ahmed.id,
            company_id=comp_apex.id,
            assigned_to_id=owner_user.id,
            title="Apex Logistics — Fleet Automation CRM Integration",
            status=LeadStatus.PROPOSAL.value,
            source="Website",
            score=88,
            priority=LeadPriority.HIGH.value,
            estimated_value=24500.0,
            notes="Ahmed is interested in the Premium package. Requested pricing and asked about implementation time.",
        )
        lead_elena = Lead(
            organization_id=org.id,
            contact_id=contact_elena.id,
            company_id=comp_cloudscale.id,
            assigned_to_id=admin_user.id,
            title="CloudScale — Multi-tenant Billing Hub",
            status=LeadStatus.NEGOTIATION.value,
            source="Referral",
            score=94,
            priority=LeadPriority.URGENT.value,
            estimated_value=48000.0,
            notes="Final terms under legal review. Security questionnaire cleared.",
        )
        lead_marcus = Lead(
            organization_id=org.id,
            contact_id=contact_marcus.id,
            company_id=comp_medtech.id,
            assigned_to_id=rep_user.id,
            title="MedTech — HIPAA Compliant Patient CRM",
            status=LeadStatus.CONTACTED.value,
            source="Cold Outreach",
            score=62,
            priority=LeadPriority.MEDIUM.value,
            estimated_value=12000.0,
            notes="Initial call completed; requested compliance whitepaper.",
        )
        session.add_all([lead_ahmed, lead_elena, lead_marcus])
        await session.flush()

        # 7. Create Deals
        deal_apex = Deal(
            organization_id=org.id,
            pipeline_id=pipeline.id,
            stage_id=stages_dict["Proposal"].id,
            contact_id=contact_ahmed.id,
            company_id=comp_apex.id,
            assigned_to_id=owner_user.id,
            title="Apex Logistics — Enterprise Rollout",
            value=24500.0,
            status=DealStatus.OPEN.value,
            win_probability=75,
            expected_close_date=now + timedelta(days=14),
            notes="Proposal sent 3 days ago.",
        )
        deal_cloudscale = Deal(
            organization_id=org.id,
            pipeline_id=pipeline.id,
            stage_id=stages_dict["Negotiation"].id,
            contact_id=contact_elena.id,
            company_id=comp_cloudscale.id,
            assigned_to_id=admin_user.id,
            title="CloudScale — Infrastructure License",
            value=48000.0,
            status=DealStatus.OPEN.value,
            win_probability=90,
            expected_close_date=now + timedelta(days=5),
        )
        deal_won_example = Deal(
            organization_id=org.id,
            pipeline_id=pipeline.id,
            stage_id=stages_dict["Won"].id,
            contact_id=contact_ahmed.id,
            company_id=comp_apex.id,
            assigned_to_id=owner_user.id,
            title="Apex Logistics — Pilot Scope Phase 1",
            value=15000.0,
            status=DealStatus.WON.value,
            win_probability=100,
            closed_at=now - timedelta(days=10),
        )
        session.add_all([deal_apex, deal_cloudscale, deal_won_example])
        await session.flush()

        # 8. Create Activity Timeline Records
        act1 = Activity(
            organization_id=org.id,
            user_id=owner_user.id,
            lead_id=lead_ahmed.id,
            contact_id=contact_ahmed.id,
            deal_id=deal_apex.id,
            activity_type=ActivityType.CALL.value,
            title="Discovery & Technical Scope Call",
            description="Discussed multi-warehouse routing and legacy API connectors. Ahmed confirmed budget approval.",
            outcome="Connected",
            duration_seconds=1680,
            performed_at=now - timedelta(days=5),
        )
        act2 = Activity(
            organization_id=org.id,
            user_id=owner_user.id,
            lead_id=lead_ahmed.id,
            contact_id=contact_ahmed.id,
            deal_id=deal_apex.id,
            activity_type=ActivityType.PROPOSAL.value,
            title="Enterprise Implementation Proposal Sent",
            description="Delivered formal 12-month proposal document ($24,500) covering implementation, onboarding, and SLA.",
            outcome="Delivered",
            performed_at=now - timedelta(days=3),
        )
        act3 = Activity(
            organization_id=org.id,
            user_id=admin_user.id,
            lead_id=lead_elena.id,
            contact_id=contact_elena.id,
            deal_id=deal_cloudscale.id,
            activity_type=ActivityType.MEETING.value,
            title="Contract Terms & SLA Negotiation",
            description="Met with Elena and legal counsel. Final pricing approved; minor clause adjustment on data residency.",
            outcome="Agreed",
            duration_seconds=2700,
            performed_at=now - timedelta(days=1),
        )
        session.add_all([act1, act2, act3])

        # 9. Create Tasks & Follow-ups (Overdue, Due Today, Upcoming)
        task_overdue = Task(
            organization_id=org.id,
            assigned_to_id=owner_user.id,
            created_by_id=owner_user.id,
            lead_id=lead_ahmed.id,
            contact_id=contact_ahmed.id,
            deal_id=deal_apex.id,
            title="Follow up regarding proposal terms with Ahmed",
            description="Proposal sent 3 days ago without reply. Check in on pricing review.",
            task_type=TaskType.FOLLOW_UP.value,
            priority=TaskPriority.HIGH.value,
            status=TaskStatus.PENDING.value,
            due_date=now - timedelta(hours=18),  # Explicitly overdue
        )
        task_today = Task(
            organization_id=org.id,
            assigned_to_id=admin_user.id,
            created_by_id=admin_user.id,
            lead_id=lead_elena.id,
            contact_id=contact_elena.id,
            deal_id=deal_cloudscale.id,
            title="Send updated Master Services Agreement to Elena",
            description="Incorporate agreed data residency clause.",
            task_type=TaskType.EMAIL.value,
            priority=TaskPriority.URGENT.value,
            status=TaskStatus.PENDING.value,
            due_date=now + timedelta(hours=4),  # Due today
        )
        task_upcoming = Task(
            organization_id=org.id,
            assigned_to_id=rep_user.id,
            created_by_id=rep_user.id,
            lead_id=lead_marcus.id,
            contact_id=contact_marcus.id,
            title="Send HIPAA compliance overview & schedule demo",
            description="Follow up on Dr. Marcus's request for healthcare whitepaper.",
            task_type=TaskType.CALL.value,
            priority=TaskPriority.MEDIUM.value,
            status=TaskStatus.PENDING.value,
            due_date=now + timedelta(days=2),  # Upcoming
        )
        session.add_all([task_overdue, task_today, task_upcoming])

        # 10. Create AI Insights Cache (Customer Summary & Explainable Priority)
        ai_insight_summary = AIInsight(
            organization_id=org.id,
            entity_type="lead",
            entity_id=lead_ahmed.id,
            insight_type=InsightType.SUMMARY.value,
            content={
                "summary": "Ahmed Khan at Apex Logistics is interested in the Premium package ($24,500). Discovery call completed and proposal delivered 3 days ago. Follow-up is now overdue.",
                "sentiment": "positive",
                "key_points": [
                    "Budget verified for $24.5k annual license",
                    "Proposal delivered 3 days ago",
                    "Follow-up task is currently overdue",
                ],
            },
            confidence=0.94,
            model_name="mock-ai-engine",
            provider_name="mock",
        )
        session.add(ai_insight_summary)

        # 11. Create Automation Rules
        rule1 = AutomationRule(
            organization_id=org.id,
            name="Auto-assign Inbound Web Leads & Create First Contact Task",
            description="Whenever a lead is created from Website, assign to sales and schedule discovery task.",
            event_trigger="lead.created",
            conditions=[{"field": "source", "operator": "equals", "value": "Website"}],
            is_active=True,
        )
        session.add(rule1)
        await session.flush()

        act_rule1 = AutomationAction(
            rule_id=rule1.id,
            action_type="create_task",
            action_config={"title": "First discovery contact", "due_in_hours": 2, "priority": "HIGH"},
            execution_order=1,
        )
        session.add(act_rule1)

        # Commit everything
        await session.commit()
        print("Database seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed_database())
