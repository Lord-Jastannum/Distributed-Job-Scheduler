import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.organization import Organization
from app.models.project import Project
from app.models.user import User
from app.schemas.organization import OrganizationCreate, OrganizationOut, ProjectCreate, ProjectOut

router = APIRouter(prefix="/api/v1", tags=["organizations"])


def _get_owned_org(db: Session, org_id: uuid.UUID, user: User) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    if org.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this organization")
    return org


@router.post("/organizations", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org = Organization(name=payload.name, owner_id=current_user.id)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@router.get("/organizations", response_model=list[OrganizationOut])
def list_organizations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    orgs = (
        db.query(Organization)
        .filter(Organization.owner_id == current_user.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return orgs


@router.get("/organizations/{org_id}", response_model=OrganizationOut)
def get_organization(org_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _get_owned_org(db, org_id, current_user)


@router.post("/organizations/{org_id}/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    org_id: uuid.UUID,
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_org(db, org_id, current_user)
    project = Project(organization_id=org_id, name=payload.name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/organizations/{org_id}/projects", response_model=list[ProjectOut])
def list_projects(
    org_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_org(db, org_id, current_user)
    projects = (
        db.query(Project)
        .filter(Project.organization_id == org_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return projects
