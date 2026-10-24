from fastapi import FastAPI

app = FastAPI(title="Free Penguins")


@app.get("/")
def home():
    return {"message": "Free Penguins is running"}


@app.get("/health")
def health():
    return {"status": "ok"}