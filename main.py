import json
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

app = FastAPI()

# Store active rooms: room_id -> set of WebSocket connections
active_rooms: dict[str, set[WebSocket]] = {}


@app.get("/")
async def get():
    return FileResponse("index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    current_room_id = None

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "create_or_join":
                room_id = message.get("roomId")

                if not room_id or room_id not in active_rooms:
                    room_id = str(uuid.uuid4())[:8]
                    active_rooms[room_id] = set()

                room = active_rooms[room_id]

                if len(room) >= 2:
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": "Room is full (max 2 users)."})
                    )
                    await websocket.close()
                    return

                current_room_id = room_id
                room.add(websocket)

                user_label = "User A" if len(room) == 1 else "User B"

                await websocket.send_text(
                    json.dumps({
                        "type": "joined",
                        "roomId": room_id,
                        "userLabel": user_label,
                        "userCount": len(room),
                    })
                )

                await broadcast_to_room(
                    room_id,
                    {"type": "user_joined", "userCount": len(room)},
                    sender=websocket,
                )

            elif message.get("type") in ["draw", "erase", "shape", "text", "clear"]:
                if current_room_id:
                    await broadcast_to_room(current_room_id, message, sender=websocket)

    except WebSocketDisconnect:
        if current_room_id and current_room_id in active_rooms:
            room = active_rooms[current_room_id]
            room.discard(websocket)

            await broadcast_to_room(
                current_room_id,
                {"type": "user_left", "userCount": len(room)},
            )

            if len(room) == 0:
                del active_rooms[current_room_id]


async def broadcast_to_room(room_id: str, payload: dict, sender: WebSocket = None):
    if room_id not in active_rooms:
        return
    message = json.dumps(payload)
    for connection in list(active_rooms[room_id]):
        if connection != sender:
            await connection.send_text(message)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="localhost", port=8000, reload=True)
