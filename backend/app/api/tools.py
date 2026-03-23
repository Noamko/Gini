from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.tool import Tool
from app.schemas.tool import ToolResponse, ToolUpdate

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
async def list_tools(offset: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db)):
    count_result = await db.execute(select(func.count(Tool.id)))
    total = count_result.scalar_one()

    result = await db.execute(
        select(Tool).order_by(Tool.name).offset(offset).limit(limit)
    )
    tools = result.scalars().all()
    return {
        "items": [ToolResponse.model_validate(t) for t in tools],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/{tool_id}")
async def get_tool(tool_id: UUID, db: AsyncSession = Depends(get_db)):
    tool = await db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return ToolResponse.model_validate(tool)


@router.put("/{tool_id}")
async def update_tool(tool_id: UUID, body: ToolUpdate, db: AsyncSession = Depends(get_db)):
    tool = await db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(tool, key, value)

    await db.commit()
    await db.refresh(tool)
    return ToolResponse.model_validate(tool)
