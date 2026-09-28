FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python scripts/build_distance_matrix.py && python scripts/build_road_network.py
EXPOSE 8000
CMD ["sh", "-c", "python scripts/seed_demo.py --n 90 && uvicorn fairtriage.api:app --host 0.0.0.0 --port 8000"]
