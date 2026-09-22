# FastAPI & LLM Document Extraction Service

This repository contains a production-grade FastAPI backend designed to process unstructured real estate documents using a self-hosted AI model (Qwen2.5 via Ollama) and store the structured output in PostgreSQL.

## Architectural Decisions

* **AI Data Parsing (Microservice Separation):** LLM integration is handled as an asynchronous HTTP request to a locally hosted Ollama server. This prevents sensitive document text from leaving our infrastructure[cite: 1]. It also separates the heavy GPU workloads from the FastAPI web workers, ensuring the API does not hang if the model is slow to load into VRAM.
* **Database Session Handling:** SQLAlchemy sessions are strictly scoped to the request lifecycle using FastAPI dependencies (`yield db`).
* **Data Integrity & PII Protection:** The application relies on PostgreSQL unique constraints to prevent race conditions. If a duplicate address is processed, the backend intercepts the `IntegrityError`, rolls back the transaction, and returns a sanitized HTTP 409 Conflict. This deliberately prevents raw database exceptions from leaking to the client, which could expose sensitive PII (like names or financials)[cite: 1].
* **Structured Output Validation:** The LLM is strictly prompted to return JSON, which is then passed through a Pydantic `BaseModel` for validation before interacting with the database.

## Tech Stack
* **Framework:** FastAPI, Uvicorn
* **Database:** PostgreSQL, SQLAlchemy (ORM)
* **AI Provider:** Ollama (Qwen2.5:14b)[cite: 1]
* **Validation:** Pydantic
