FROM node:latest as builder

WORKDIR /src
COPY frontend .
RUN npm install
RUN npm run build

FROM python:3.12-slim

WORKDIR /src
RUN pip install pipenv
COPY pyserver/Pipfile pyserver/Pipfile.lock .
RUN pipenv install --system
COPY pyserver .

COPY --from=builder /src/dist static/

CMD ["python", "-m", "dfh"]

