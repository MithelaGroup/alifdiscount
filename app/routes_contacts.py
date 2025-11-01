# app/routes_contacts.py
from fastapi import APIRouter, HTTPException, Depends, status, Form, Request
from sqlalchemy.orm import Session
import re

from .db import SessionLocal
from .models import Contact

router = APIRouter(prefix="/api/contacts", tags=["contacts"])

BD_REGEX = re.compile(r"^\+8801\d{9}$")  # 10 digits after +880

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("")
def list_contacts(page: int = 1, per_page: int = 10, db: Session = Depends(get_db)):
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 10
    q = db.query(Contact)
    total = q.count()
    rows = (
        q.order_by(Contact.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    data = [
        {
            "id": c.id,
            "full_name": c.full_name,
            "mobile": c.mobile,
            "remarks": c.remarks or "",
            "created_at": c.created_at.isoformat()
        }
        for c in rows
    ]
    return {"total": total, "page": page, "per_page": per_page, "rows": data}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_contact(
    full_name: str = Form(...),
    mobile: str = Form(...),
    remarks: str = Form(""),
    db: Session = Depends(get_db),
):
    mobile = mobile.strip()
    if not BD_REGEX.match(mobile):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid BD number. Use +8801XXXXXXXXX (10 digits after +880).",
        )

    # Enforce uniqueness by mobile
    exists = db.query(Contact).filter(Contact.mobile == mobile).first()
    if exists:
        raise HTTPException(status_code=409, detail="Mobile already exists")

    item = Contact(full_name=full_name.strip(), mobile=mobile, remarks=remarks.strip() or None)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id}
