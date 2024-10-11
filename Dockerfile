# ----------------------------------------------------------------------
# Build React Frontend
# ----------------------------------------------------------------------
FROM node:latest as builder

WORKDIR /src
COPY frontend .
RUN npm install
RUN npm run build

# ----------------------------------------------------------------------
# Build Python Backend and copy frontend assets into `static/` folder.
# ----------------------------------------------------------------------
FROM python:3.12-slim

# Copy Pipfile and install dependencies.
WORKDIR /src
RUN pip install pipenv
COPY backend/Pipfile backend/Pipfile.lock .
RUN pipenv install --system

# Copy everything else.
COPY backend .

# Copy the frontend assets.
COPY --from=builder /src/dist static/

CMD ["python", "-m", "dfh"]

