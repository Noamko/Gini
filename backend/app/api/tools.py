from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.tool import Tool
from app.schemas.tool import ToolCreate, ToolResponse, ToolUpdate

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
async def list_tools(offset: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db)):
    count_result = await db.execute(select(func.count(Tool.id)))
    total = count_result.scalar_one()

    result = await db.execute(
        select(Tool).order_by(Tool.is_builtin.desc(), Tool.name).offset(offset).limit(limit)
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


@router.get("/{tool_id}/source")
async def get_tool_source(tool_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get the Python source code of a built-in tool."""
    tool = await db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    if tool.code:
        return {"source": tool.code}

    # For built-in tools, read the source file
    if tool.is_builtin:
        try:
            import inspect

            from app.tools.registry import get_tool as get_builtin
            builtin = get_builtin(tool.name)
            if builtin:
                source = inspect.getsource(type(builtin))
                return {"source": source}
        except Exception:
            pass

    return {"source": f"# Source not available for {tool.name}"}


@router.post("", status_code=201)
async def create_tool(body: ToolCreate, db: AsyncSession = Depends(get_db)):
    """Create a custom tool with Python code."""
    tool = Tool(
        name=body.name,
        description=body.description,
        parameters_schema=body.parameters_schema,
        implementation="custom",
        code=body.code,
        requires_sandbox=body.requires_sandbox,
        requires_approval=body.requires_approval,
        is_builtin=False,
        is_active=True,
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return ToolResponse.model_validate(tool)


@router.post("/upload", status_code=201)
async def upload_tool(
    name: str = Form(...),
    description: str = Form(""),
    requires_sandbox: bool = Form(False),
    requires_approval: bool = Form(False),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Create a custom tool from an uploaded Python file."""
    code = (await file.read()).decode("utf-8")
    tool = Tool(
        name=name,
        description=description or f"Custom tool: {name}",
        parameters_schema={"type": "object", "properties": {}},
        implementation="custom",
        code=code,
        requires_sandbox=requires_sandbox,
        requires_approval=requires_approval,
        is_builtin=False,
        is_active=True,
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
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


@router.delete("/{tool_id}", status_code=204)
async def delete_tool(tool_id: UUID, db: AsyncSession = Depends(get_db)):
    tool = await db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    if tool.is_builtin:
        raise HTTPException(status_code=400, detail="Cannot delete built-in tools")
    await db.delete(tool)
    await db.commit()
