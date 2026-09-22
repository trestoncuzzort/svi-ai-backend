from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.exc import IntegrityError
import httpx
import json
from fastapi.security import OAuth2PasswordBearer
import jwt
from datetime import datetime, timedelta, timezone
import uuid
import time

# DATABASE CONFIGURATION
DATABASE_URL = "postgresql://ai_worker: @localhost/svi_db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# SQLALCHEMY MODEL (Database Table)
class PropertyRecord(Base):
	__tablename__ = "properties"
	id = Column(Integer, primary_key=True, index=True)
	address = Column(String, unique=True , nullable=False)
	valuation = Column(Integer, nullable=False)

# pydantic schema (Request validation)
class PropertyCreate(BaseModel):
   address: str
   valuation: int

class DocumentInput(BaseModel):
   text: str

# jwt authentication config
SECRET_KEY = "stewart_valuation_intelligence_mock_key"
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_jwt_token(token: str = Depends(oauth2_scheme)):
    try:
        # Pinned algorithm to prevent none-algorithm attacks
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token payload.")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token signature.")

# fastapi application
app = FastAPI()

# endpoint to generate a test token
@app.get("/token")
def generate_test_token():
    expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    token = jwt.encode({"sub": "admin_user", "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}

# Dependency to handle the database session per request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
         db.close()

# post endpoint
@app.post("/properties/")
def create_property(
    prop: PropertyCreate,
    db: Session = Depends(get_db),
    user_id: str = Depends(verify_jwt_token)
):
    #creates new property when token authorizes
    new_property = PropertyRecord(address=prop.address, valuation=prop.valuation)
    db.add(new_property)

    try:
        db.commit()
        db.refresh(new_property)
        return {"status": "success", "data": new_property}

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A property with that address already exists.")

# streaming ai endpoint
@app.post("/stream-extract/")
async def stream_extract(doc: DocumentInput, user_id: str = Depends(verify_jwt_token)):
    payload = {
         "model": "qwen2.5:14b",
         "prompt": f"Extract the property address and valuation from this text. Return ONLY a valid JSON object with keys 'address' and 'valuation'. Text: {doc.text}",
         "stream": True  # <--- Changed to True for streaming
    }

    async def generate_tokens():
        # Open an async stream to Ollama
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", "http://localhost:11434/api/generate", json=payload, timeout=60.0) as response:
                response.raise_for_status()
                # Yield tokens as they arrive via Server-Sent Events (SSE)
                async for chunk in response.aiter_lines():
                    if chunk:
                        data = json.loads(chunk)
                        if "response" in data:
                            yield f"data: {data['response']}\n\n"

    return StreamingResponse(generate_tokens(), media_type="text/event-stream")

# the ai extraction endpoint
@app.post("/extract/")
def extract_and_save(doc: DocumentInput, db: Session = Depends(get_db)):
    payload = {
         "model": "qwen2.5:14b",
	 "prompt": f"Extract the property address and valuation from this text. return ONLY a valid JSON object with keys 'address' and 'valuation'. Do not include markdown or explanations. Text: {doc.text}",
	 "stream": False
    }

# 2. Send the text to GPU via internal HTTP request

    # I used a 60-second timeout to allow model into VRAM if it is idle
    response = httpx.post("http://localhost:11434/api/generate", json=payload, timeout=60.0)
    response.raise_for_status()

    # 3 parse the LLM output back into a python dictionary
    llm_output = response.json()["response"]
    extracted_data = json.loads(llm_output)

# 4 save the extracted data using the exact same safety checks as before
    new_property = PropertyRecord(
        address=extracted_data["address"],
        valuation=int(extracted_data["valuation"])
    )
    db.add(new_property)

    try:
        db.commit()
        db.refresh(new_property)
        return {"status": "success", "source": "ai_extraction", "data": new_property}

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A property with that extracted address already exists.")

# ASYNC JOB PIPELINE (202 ACCEPTED)
def process_document_worker(job_id: str, text: str):
    # sqs / celery worker
    print(f"[WORKER] Job {job_id} started...")
    time.sleep(5)  # simulate heavy processing time
    print(f"[WORKER] Job {job_id} finished processing document!")
    # sdh

@app.post("/async-extract/", status_code=status.HTTP_202_ACCEPTED)
async def async_extract(
    doc: DocumentInput,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(verify_jwt_token)
):
    # Generate a unique tracking ID for the client
    job_id = str(uuid.uuid4())

    # Hand the heavy lifting off to the background worker
    background_tasks.add_task(process_document_worker, job_id, doc.text)

    # Immediately return 202 Accepted to the client so they don't block
    return {
        "status": "accepted",
        "job_id": job_id,
        "message": "Document received. Processing in the background."
    }
