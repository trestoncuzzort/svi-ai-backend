# Real Estate AI Extraction Microservice

**Note:** This repository serves as the functional proof-of-concept and technical implementation for the pre-interview questionnaire provided by Stewart Valuation Intelligence. It demonstrates production-grade architectural patterns, security standards, and asynchronous data processing pipelines discussed in the technical assessment.

## Overview

This FastAPI microservice extracts property addresses and valuations from unstructured text using a local LLM (Qwen 2.5 via Ollama). By keeping the LLM inference localized (or on private EC2 instances in production), it inherently protects PII and sensitive real estate data from third-party API leakage. 

## Architectural Requirements Implemented

1. **JWT-Based Authentication**
   - Endpoints are secured using PyJWT with a pinned HS256 algorithm.
   - Token signatures and expiration times are explicitly verified *before* database sessions are opened.
   - Unauthenticated or expired requests are cleanly rejected with `401 Unauthorized`.

2. **Controlled Schema Migrations (Alembic)**
   - Auto-table generation (`create_all`) has been removed in favor of Alembic migrations.
   - This supports the "expand-and-contract" deployment strategy required for zero-downtime database updates on a live PostgreSQL instance.

3. **Real-Time AI Streaming (SSE)**
   - The `/stream-extract/` endpoint utilizes FastAPI's `StreamingResponse` to forward AI-generated tokens asynchronously from the Ollama server to the client via Server-Sent Events. 
   - This eliminates long loading spinners for the end user.

4. **Asynchronous Job Queues (202 Accepted)**
   - The `/async-extract/` endpoint implements a non-blocking API contract for massive document payloads.
   - It immediately returns an `HTTP 202 Accepted` status with a unique `job_id`, while offloading the heavy extraction process to a background worker (simulating an SQS/Celery pipeline).

5. **Data Integrity & Error Handling**
   - PostgreSQL `UNIQUE` constraints ensure duplicate property addresses are caught at the database level.
   - `IntegrityError` exceptions securely roll back the database session and return a clean `409 Conflict` error without leaking backend state or PII.

## Tech Stack
* **Framework:** FastAPI
* **Database:** PostgreSQL & SQLAlchemy ORM
* **Migrations:** Alembic
* **AI Engine:** Ollama (Qwen 2.5:14b)
* **Security:** PyJWT
