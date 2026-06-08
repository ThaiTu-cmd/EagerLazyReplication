import os
import time
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import requests
from sqlalchemy import create_engine, Column, String, Float
from sqlalchemy.orm import sessionmaker, declarative_base

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="/app/templates")

NODE_NAME = os.getenv("NODE_NAME", "Unknown_Node")
NODE_TYPE = os.getenv("NODE_TYPE", "REPLICA")
NODE_TABLE = os.getenv("NODE_TABLE", "node_a")
REPLICAS_ENV = os.getenv("REPLICAS", "")
REPLICAS = [r.strip() for r in REPLICAS_ENV.split(",") if r.strip()]

DB_HOST = os.getenv("DB_HOST", "host.docker.internal")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "appuser")
DB_PASS = os.getenv("DB_PASS", "apppass")
DB_NAME = os.getenv("DB_NAME", "replication_db")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class TransactionModel(Base):
    __tablename__ = NODE_TABLE
    __table_args__ = {"extend_existing": True}
    Transaction_ID = Column(String(50), primary_key=True, index=True)
    Account_ID = Column(String(50))
    Timestamp = Column(String(50))
    Transaction_Type = Column(String(50))
    Amount = Column(Float)
    Status = Column(String(50))


Base.metadata.create_all(bind=engine)


class Transaction(BaseModel):
    Transaction_ID: str
    Account_ID: str
    Timestamp: str
    Transaction_Type: str
    Amount: float
    Status: str


def async_replicate_task(replica_url: str, tx_data: dict):
    try:
        time.sleep(0.01)
        requests.post(f"{replica_url}/replicate", json=tx_data, timeout=2)
    except Exception:
        pass


def clear_local_storage() -> int:
    db = SessionLocal()
    deleted_count = db.query(TransactionModel).delete()
    db.commit()
    db.close()
    return deleted_count


@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"node_name": NODE_NAME, "node_type": NODE_TYPE}
    )


@app.post("/write")
def write_transaction(tx: Transaction, mode: str, background_tasks: BackgroundTasks):
    if NODE_TYPE != "PRIMARY":
        raise HTTPException(
            status_code=400, detail="Only Primary Node can accept writes")

    db = SessionLocal()
    tx_dict = tx.model_dump()
    tx_dict["Status"] = "COMPLETED"

    new_tx = TransactionModel(**tx_dict)
    db.add(new_tx)
    db.commit()
    db.close()

    if mode == "eager":
        for replica in REPLICAS:
            try:
                res = requests.post(
                    f"{replica}/replicate", json=tx_dict, timeout=2)
                if res.status_code != 200:
                    pass
            except Exception:
                pass
        return {"status": "SUCCESS", "mode": "eager"}

    elif mode == "lazy":
        for replica in REPLICAS:
            background_tasks.add_task(async_replicate_task, replica, tx_dict)
        return {"status": "SUCCESS", "mode": "lazy"}

    raise HTTPException(
        status_code=400, detail="Mode must be 'eager' or 'lazy'")


@app.post("/replicate")
def replicate_transaction(tx: Transaction):
    db = SessionLocal()
    exists = db.query(TransactionModel).filter(
        TransactionModel.Transaction_ID == tx.Transaction_ID).first()
    if not exists:
        new_tx = TransactionModel(**tx.model_dump())
        db.add(new_tx)
        db.commit()
    db.close()
    return {"status": "REPLICATED"}


@app.get("/check/{transaction_id}")
def check_transaction(transaction_id: str):
    db = SessionLocal()
    exists = db.query(TransactionModel).filter(
        TransactionModel.Transaction_ID == transaction_id).first() is not None
    db.close()
    return {
        "exists": exists,
        "node_name": NODE_NAME,
        "node_type": NODE_TYPE,
    }


@app.get("/metrics")
def get_metrics():
    db = SessionLocal()
    count = db.query(TransactionModel).count()
    db.close()
    return {
        "node_name": NODE_NAME,
        "node_type": NODE_TYPE,
        "total_records": count
    }


@app.post("/reset-local")
def reset_local_storage():
    deleted = clear_local_storage()
    return {
        "status": "RESET_OK",
        "node_name": NODE_NAME,
        "deleted_records": deleted,
    }


@app.get("/data")
def get_data(limit: int = 100):
    """Trả về danh sách transaction trong table của node này."""
    db = SessionLocal()
    records = db.query(TransactionModel).limit(limit).all()
    db.close()
    return {
        "node_name": NODE_NAME,
        "node_type": NODE_TYPE,
        "table": TransactionModel.__tablename__,
        "count": len(records),
        "records": [
            {
                "Transaction_ID": r.Transaction_ID,
                "Account_ID": r.Account_ID,
                "Timestamp": r.Timestamp,
                "Transaction_Type": r.Transaction_Type,
                "Amount": r.Amount,
                "Status": r.Status,
            }
            for r in records
        ],
    }


@app.post("/reset-all")
def reset_all_nodes():
    if NODE_TYPE != "PRIMARY":
        raise HTTPException(
            status_code=400, detail="Only Primary Node can reset all nodes")

    result = {
        "status": "RESET_OK",
        "primary": {
            "node_name": NODE_NAME,
            "deleted_records": clear_local_storage(),
        },
        "replicas": [],
    }

    for replica in REPLICAS:
        try:
            res = requests.post(f"{replica}/reset-local", timeout=3)
            if res.status_code == 200:
                result["replicas"].append(res.json())
            else:
                result["replicas"].append(
                    {
                        "status": "RESET_FAIL",
                        "replica": replica,
                        "http_status": res.status_code,
                    }
                )
        except Exception:
            result["replicas"].append(
                {
                    "status": "RESET_FAIL",
                    "replica": replica,
                    "http_status": "unreachable",
                }
            )

    return result
