FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY scripting/ scripting/
COPY web/ web/
COPY data/ data/
COPY images/ images/
COPY videos/ videos/

# AI_MODE defaults to "local" (no API key needed) if unset - see README.
# Mount/override a real .env, or pass -e AI_MODE=groq -e GROQ_API_KEY=... ,
# for the Groq-backed mode.
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
