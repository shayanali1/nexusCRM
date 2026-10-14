from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import BadRequestException, NotFoundException
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal, DealStatus
from app.modules.leads.models import Lead, LeadStatus
from app.modules.leads.repository import LeadRepository
from app.modules.leads.schemas import LeadConvertRequest, LeadCreate, LeadResponse, LeadUpdate
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.users.models import User


class LeadService:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id
        self.repo = LeadRepository(db, organization_id)

    def _to_response(self, lead: Lead) -> LeadResponse:
        resp = LeadResponse.model_validate(lead)
        if lead.contact:
            resp.contact_name = lead.contact.full_name
            resp.contact_email = lead.contact.email
            resp.contact_phone = lead.contact.phone
        if lead.company:
            resp.company_name = lead.company.name
        if lead.assigned_to:
            resp.assigned_to_name = lead.assigned_to.full_name
        return resp

    async def list_leads(
        self,
        status: Optional[str] = None,
        assigned_to_id: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[LeadResponse]:
        leads = await self.repo.list_all(status, assigned_to_id, search, limit, offset)
        return [self._to_response(l) for l in leads]

    async def get_lead(self, lead_id: str) -> LeadResponse:
        lead = await self.repo.get_by_id(lead_id)
        if not lead:
            raise NotFoundException("Lead not found.")
        return self._to_response(lead)

    async def create_lead(self, data: LeadCreate) -> LeadResponse:
        contact_id = data.contact_id
        company_id = data.company_id
        assigned_to_id = data.assigned_to_id

        # 1. Validate or resolve company
        if company_id:
            c_stmt = select(Company.id).where(Company.id == company_id, Company.organization_id == self.org_id)
            if not (await self.db.execute(c_stmt)).scalar_one_or_none():
                raise NotFoundException("Company not found.")
        elif data.company_name:
            company = Company(
                organization_id=self.org_id,
                name=data.company_name,
            )
            self.db.add(company)
            await self.db.flush()
            company_id = company.id

        # 2. Validate or resolve contact
        if contact_id:
            ct_stmt = select(Contact.id).where(Contact.id == contact_id, Contact.organization_id == self.org_id)
            if not (await self.db.execute(ct_stmt)).scalar_one_or_none():
                raise NotFoundException("Contact not found.")
        elif data.contact_name:
            parts = data.contact_name.strip().split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""
            contact = Contact(
                organization_id=self.org_id,
                company_id=company_id,
                first_name=first_name,
                last_name=last_name or first_name,
                email=data.contact_email,
                phone=data.contact_phone,
                lead_source=data.source,
            )
            self.db.add(contact)
            await self.db.flush()
            contact_id = contact.id

        # 3. Validate assigned user
        if assigned_to_id:
            u_stmt = select(User.id).where(
                User.id == assigned_to_id,
                User.organization_id == self.org_id,
                User.is_active.is_(True),
            )
            if not (await self.db.execute(u_stmt)).scalar_one_or_none():
                raise NotFoundException("User not found.")

        data.contact_id = contact_id
        data.company_id = company_id
        data.assigned_to_id = assigned_to_id
        lead = await self.repo.create(data)

        from app.core.events import CRMEvent, CRMEventType, event_dispatcher
        await event_dispatcher.dispatch(
            CRMEvent(
                event_name=CRMEventType.LEAD_CREATED,
                organization_id=self.org_id,
                entity_type="lead",
                entity_id=lead.id,
                payload={
                    "lead_id": lead.id,
                    "title": lead.title,
                    "assigned_to_id": lead.assigned_to_id,
                },
            ),
            self.db,
        )

        loaded = await self.repo.get_by_id(lead.id)
        return self._to_response(loaded or lead)

    async def update_lead(self, lead_id: str, data: LeadUpdate) -> LeadResponse:
        lead = await self.repo.get_by_id(lead_id)
        if not lead:
            raise NotFoundException("Lead not found.")

        update_dict = data.model_dump(exclude_unset=True)

        if "company_id" in update_dict and update_dict["company_id"] is not None:
            c_stmt = select(Company.id).where(Company.id == update_dict["company_id"], Company.organization_id == self.org_id)
            if not (await self.db.execute(c_stmt)).scalar_one_or_none():
                raise NotFoundException("Company not found.")

        if "contact_id" in update_dict and update_dict["contact_id"] is not None:
            ct_stmt = select(Contact.id).where(Contact.id == update_dict["contact_id"], Contact.organization_id == self.org_id)
            if not (await self.db.execute(ct_stmt)).scalar_one_or_none():
                raise NotFoundException("Contact not found.")

        if "assigned_to_id" in update_dict and update_dict["assigned_to_id"] is not None:
            u_stmt = select(User.id).where(
                User.id == update_dict["assigned_to_id"],
                User.organization_id == self.org_id,
                User.is_active.is_(True),
            )
            if not (await self.db.execute(u_stmt)).scalar_one_or_none():
                raise NotFoundException("User not found.")

        updated = await self.repo.update(lead, data)
        loaded = await self.repo.get_by_id(updated.id)
        return self._to_response(loaded or updated)

    async def convert_lead(self, lead_id: str, req: LeadConvertRequest) -> dict:
        """Convert a qualified lead into an active sales Deal and customer record."""
        lead = await self.repo.get_by_id(lead_id)
        if not lead:
            raise NotFoundException("Lead not found.")

        if lead.converted_to_deal_id is not None or lead.converted_at is not None:
            raise BadRequestException("Lead has already been converted to a deal.")

        pipeline_id = req.pipeline_id
        stage_id = req.stage_id

        # 1. Resolve & validate pipeline
        if pipeline_id:
            pipe_stmt = select(Pipeline).where(
                Pipeline.id == pipeline_id,
                Pipeline.organization_id == self.org_id,
            )
            pipeline = (await self.db.execute(pipe_stmt)).scalars().first()
            if not pipeline:
                raise NotFoundException("Pipeline not found.")
        else:
            pipe_stmt = (
                select(Pipeline)
                .where(Pipeline.organization_id == self.org_id)
                .order_by(Pipeline.is_default.desc(), Pipeline.created_at)
            )
            pipeline = (await self.db.execute(pipe_stmt)).scalars().first()
            if not pipeline:
                raise BadRequestException("No sales pipeline configured for this organization.")
            pipeline_id = pipeline.id

        # 2. Resolve & validate stage
        if stage_id:
            stage_stmt = select(PipelineStage).where(
                PipelineStage.id == stage_id,
                PipelineStage.organization_id == self.org_id,
            )
            stage = (await self.db.execute(stage_stmt)).scalars().first()
            if not stage:
                raise NotFoundException("Pipeline stage not found.")
            if stage.pipeline_id != pipeline_id:
                raise BadRequestException("Pipeline stage does not belong to the selected pipeline.")
        else:
            stage_stmt = (
                select(PipelineStage)
                .where(
                    PipelineStage.pipeline_id == pipeline_id,
                    PipelineStage.organization_id == self.org_id,
                )
                .order_by(PipelineStage.order)
            )
            stage = (await self.db.execute(stage_stmt)).scalars().first()
            if not stage:
                raise BadRequestException("Pipeline has no stages configured.")
            stage_id = stage.id

        deal = Deal(
            organization_id=self.org_id,
            pipeline_id=pipeline_id,
            stage_id=stage_id,
            contact_id=lead.contact_id,
            company_id=lead.company_id,
            assigned_to_id=lead.assigned_to_id,
            title=req.deal_title or f"Deal: {lead.title}",
            value=req.deal_value if req.deal_value is not None else lead.estimated_value,
            currency=lead.currency,
            status=DealStatus.OPEN.value,
        )
        self.db.add(deal)
        await self.db.flush()

        lead.status = LeadStatus.QUALIFIED.value
        lead.converted_at = datetime.now(timezone.utc)
        lead.converted_to_deal_id = deal.id
        await self.db.commit()

        return {
            "success": True,
            "message": "Lead converted successfully to Deal.",
            "lead_id": lead.id,
            "deal_id": deal.id,
        }

    async def delete_lead(self, lead_id: str) -> None:
        lead = await self.repo.get_by_id(lead_id)
        if not lead:
            raise NotFoundException("Lead not found.")
        await self.repo.delete(lead)
