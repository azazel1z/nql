import json
import logging
import os
import asyncio
import re
from dotenv import load_dotenv
import secrets
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Depends, HTTPException, status, Header, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from deepagents import create_deep_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware

from database import get_db, SessionLocal, User, Thread, Message
from auth import get_password_hash, verify_password, create_access_token, get_current_user_cookie
from agent import get_sql_subagent, web_business_subagent, main_system_prompt

load_dotenv()

ADMIN_SECRET = os.getenv('ADMIN_SECRET')
TURNSTILE_SECRET = os.getenv('TURNSTILE_SECRET')

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logger.addHandler(handler)

agent = None
memory = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent, memory
    
    logger.info("Starting up — initialising agent and memory")
    
    async with AsyncSqliteSaver.from_conn_string("checkpoints.sqlite") as memory:
        await memory.setup()
        logger.debug("SQLite checkpointer ready")

        agent = create_deep_agent(
            model="claude-haiku-4-5",
            system_prompt=main_system_prompt,
            subagents=[get_sql_subagent(), web_business_subagent],
            checkpointer=memory,
            middleware=[
                ModelCallLimitMiddleware(run_limit=15),
                ToolCallLimitMiddleware(run_limit=30)    
            ]
        )
        logger.info("Agent initialised successfully")
        yield
    
    logger.info("Shutting down — agent and memory released")

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://challenges.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self' https://challenges.cloudflare.com; "
            "frame-src https://challenges.cloudflare.com; "
            "object-src 'none'; "
            "frame-ancestors 'none';"
        )
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
    
app = FastAPI(
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(SecurityHeadersMiddleware)

@app.get("/api/")
async def root():
    """Health check endpoint with API metadata."""
    if agent is None or memory is None:
        logger.warning("Health check hit but agent/memory not ready")
        raise HTTPException(
            status_code=503,
            detail={
                "name": "NQL",
                "version": "0.1.0",
                "description": "A deep-agent assistant with SQL and web capabilities.",
                "docs": "/docs",
                "status": "not ready"
            }
        )
    return {
        "name": "NQL",
        "version": "0.1.0",
        "description": "A deep-agent assistant with SQL and web capabilities.",
        "docs": "/docs",
        "status": "ready"
    }

class UserCreate(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    message: str

@app.post("/api/auth/register")
def register(
    user: UserCreate,
    db: Session = Depends(get_db),
    x_admin_secret: str = Header(default=None)
):
    if not ADMIN_SECRET:
        raise HTTPException(status_code=503, detail="Registration is disabled")
    if not x_admin_secret or not secrets.compare_digest(x_admin_secret, ADMIN_SECRET):
        raise HTTPException(status_code=403, detail="Forbidden")

    logger.info("Register attempt for username='%s'", user.username)
    if db.query(User).filter(User.username == user.username).first():
        logger.warning("Register failed — username='%s' already exists", user.username)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already registered")
    
    new_user = User(username=user.username, hashed_password=get_password_hash(user.password))
    db.add(new_user)
    db.commit()
    logger.info("User registered successfully username='%s'", user.username)
    return {"message": "User created successfully"}


@app.post("/api/auth/login")
async def login(response: Response, request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    if not re.match(r"^[a-zA-Z0-9._@-]+$", form_data.username):
        raise HTTPException(status_code=400, detail="Invalid username format")
    if not 3 <= len(form_data.username) <= 32:
        raise HTTPException(status_code=400, detail="Invalid username length")
    body = await request.form()
    cf_token = body.get("cf_token", "")
    if not cf_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Captcha token missing")
    
    async with httpx.AsyncClient() as client:
        cf_response = await client.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            json={
                "secret": TURNSTILE_SECRET,
                "response": cf_token,
            }
        )
    cf_result = cf_response.json()
    if not cf_result.get("success"):
        logger.warning("Turnstile verification failed for username='%s'", form_data.username)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Captcha verification failed")

    logger.info("Login attempt for username='%s'", form_data.username)
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        logger.warning("Login failed — bad credentials for username='%s'", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    logger.info("Login successful for username='%s' user_id=%s", form_data.username, user.id)
    response.set_cookie(
        key="session",
        value=access_token,
        httponly=True,        
        secure=True,          
        samesite="strict",    
        max_age=60 * 60 * 8,  
    )
    
    return {"username": form_data.username}

@app.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie("session")
    return {"message": "Logged out"}

@app.get("/api/auth/me")
async def get_me(current_user: User = Depends(get_current_user_cookie)):
    return {"username": current_user.username}

@app.post("/api/chats")
def create_chat(db: Session = Depends(get_db), current_user: User = Depends(get_current_user_cookie)):
    """Creates a new chat thread."""
    logger.debug("Creating new thread for user_id=%s", current_user.id)
    new_thread = Thread(user_id=current_user.id)
    db.add(new_thread)
    db.commit()
    db.refresh(new_thread)
    logger.info("Thread created thread_id=%s user_id=%s", new_thread.id, current_user.id)
    return {"thread_id": new_thread.id}

@app.get("/api/chats")
def list_chats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user_cookie)):
    """Lists all chats for the sidebar."""
    threads = db.query(Thread).filter(Thread.user_id == current_user.id).order_by(Thread.created_at.desc()).all()
    logger.debug("Listed %d threads for user_id=%s", len(threads), current_user.id)
    return [{"id": t.id, "title": t.title} for t in threads]

@app.get("/api/chats/{thread_id}/messages")
def get_chat_history(thread_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_cookie)):
    """Loads chat history for the UI."""
    thread = db.query(Thread).filter(Thread.id == thread_id, Thread.user_id == current_user.id).first()
    if not thread:
        logger.warning("Chat history not found thread_id=%s user_id=%s", thread_id, current_user.id)
        raise HTTPException(status_code=404, detail="Chat not found")
        
    messages = db.query(Message).filter(Message.thread_id == thread_id).order_by(Message.created_at.asc()).all()
    logger.debug("Loaded %d messages for thread_id=%s user_id=%s", len(messages), thread_id, current_user.id)
    return [{"role": m.role, "content": m.content} for m in messages]

@app.delete("/api/chats/{thread_id}")
def delete_chat(
    thread_id: str, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user_cookie)
):
    """Deletes a chat thread and all associated messages."""
    logger.info("Delete request for thread_id=%s user_id=%s", thread_id, current_user.id)
    thread = db.query(Thread).filter(
        Thread.id == thread_id, 
        Thread.user_id == current_user.id
    ).first()
    
    if not thread:
        logger.warning("Delete failed — thread not found thread_id=%s user_id=%s", thread_id, current_user.id)
        raise HTTPException(status_code=404, detail="Chat not found")
        
    db.delete(thread)
    db.commit()
    logger.info("Thread deleted thread_id=%s user_id=%s", thread_id, current_user.id)
    return {"message": "Chat deleted successfully"}

@app.post("/api/chats/{thread_id}/stream")
async def stream_chat(
    thread_id: str, 
    request: ChatRequest, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user_cookie)
):
    """Takes user input, streams LLM response via SSE, and saves to DB."""
    
    thread = db.query(Thread).filter(Thread.id == thread_id, Thread.user_id == current_user.id).first()
    if not thread:
        logger.warning("Stream request for missing thread thread_id=%s user_id=%s", thread_id, current_user.id)
        raise HTTPException(status_code=404, detail="Chat not found")

    user_msg = Message(thread_id=thread_id, role="user", content=request.message)
    db.add(user_msg)
    db.commit()

    async def event_generator():
        config = {"configurable": {"thread_id": thread_id}}
        full_assistant_response = ""
        logger.info("Stream started thread_id=%s user_id=%s", thread_id, current_user.id)
        
        try:
            async for event in agent.astream_events(
                {"messages": [{"role": "user", "content": request.message}]},
                config=config,
                version="v2"
            ):
                kind = event["event"]
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if isinstance(chunk.content, list):
                        for block in chunk.content:
                            if isinstance(block, dict):
                                text = block.get("text", "")
                                if text:
                                    full_assistant_response += text
                                    yield f"data: {json.dumps({'token': text})}\n\n"
                    
                    elif isinstance(chunk.content, str) and chunk.content:
                        full_assistant_response += chunk.content
                        yield f"data: {json.dumps({'token': chunk.content})}\n\n"
            
            logger.info(
                "Stream completed thread_id=%s user_id=%s response_chars=%d",
                thread_id, current_user.id, len(full_assistant_response)
            )

            def save_assistant_msg():
                db_local = SessionLocal()  
                try:
                    local_thread = db_local.query(Thread).filter(Thread.id == thread_id).first()
                    if local_thread and local_thread.title == "New Chat":
                        local_thread.title = request.message[:30] + "..."
                    
                    asst_msg = Message(thread_id=thread_id, role="assistant", content=full_assistant_response)
                    db_local.add(asst_msg)
                    db_local.commit()
                    logger.debug("Assistant message saved to DB thread_id=%s", thread_id)
                finally:
                    db_local.close() 
            
            await asyncio.to_thread(save_assistant_msg)
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            logger.error(
                "Stream error thread_id=%s user_id=%s error=%s",
                thread_id, current_user.id, str(e),
                exc_info=True
            )
            error_msg = "Something went wrong. Please try again."
            
            def save_error_msg():
                db_local = SessionLocal()
                try:
                    asst_msg = Message(thread_id=thread_id, role="assistant", content=error_msg)
                    db_local.add(asst_msg)
                    db_local.commit()
                    logger.debug("Error message saved to DB thread_id=%s", thread_id)
                finally:
                    db_local.close()
            
            await asyncio.to_thread(save_error_msg)
            yield f"data: {json.dumps({'token': error_msg})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")