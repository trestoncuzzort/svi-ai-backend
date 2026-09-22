from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.exc import IntegrityError
import httpx
import json

# --- DATABASE CONFIGURATION ---
DATABASE_URL = "postgresql://ai_worker: @localhost/svi_db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- SQLALCHEMY MODEL (Database Table) ---
class PropertyRecord(Base):
	__tablename__ = "properties"
	id = Column(Integer, primary_key=True, index=True)
	address = Column(String, unique=True , nullable=False)
	valuation = Column(Integer, nullable=False)

# Automatic table creator in postgres
Base.metadata.create_all(bind=engine)

# --- pydantic schema (Request validation) ---
class PropertyCreate(BaseModel):
   address: str
   valuation: int

class DocumentInput(BaseModel):
   text: str

# fastapi application
app = FastAPI()

# Dependency to handle the database session per request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
         db.close()

# POST ENDPOINT
@app.post("/properties/")
def create_property(prop: PropertyCreate, db: Session = Depends(get_db)):
    new_property = PropertyRecord(address=prop.address, valuation=prop.valuation)
    db.add(new_property)

    try:
        db.commit()
        db.refresh(new_property)
        return {"status": "success", "data": new_property}

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A property with that address already exists.")


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
