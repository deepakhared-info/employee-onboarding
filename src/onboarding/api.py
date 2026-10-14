from fastapi import APIRouter


router = APIRouter()

@router.post('/employee/import')
def import_employee():
    return {"status": "ok"}