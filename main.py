import json
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

app = FastAPI()

# Store active rooms: room_id -> set of WebSocket connections
active_rooms: dict[str, set[WebSocket]] = {}

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>2-User Real-Time Workspace</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: sans-serif; }
    body { display: flex; flex-direction: column; align-items: center; background: #f4f4f9; padding: 20px; }
    h1 { margin-bottom: 10px; color: #333; }
    #session-info { margin-bottom: 15px; padding: 10px 20px; background: #fff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }
    #toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 15px; flex-wrap: wrap; justify-content: center; background: #fff; padding: 10px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .tool-group { display: flex; gap: 4px; border-right: 1px solid #ddd; padding-right: 8px; margin-right: 4px; }
    button, input[type="color"], input[type="range"] { padding: 6px 12px; border: 1px solid #ccc; border-radius: 4px; cursor: pointer; font-size: 14px; }
    button.tool-btn { background: #e9ecef; color: #333; border: 1px solid #ced4da; }
    button.tool-btn.active { background: #007bff; color: white; border-color: #0056b3; }
    button#clear-btn { background: #dc3545; color: white; border: none; }
    button#clear-btn:hover { background: #bd2130; }
    #canvas-container { position: relative; background: white; border: 2px solid #ccc; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); width: 700px; height: 450px; }
    canvas { position: absolute; top: 0; left: 0; display: block; }
    #drawing-canvas { z-index: 1; }
    #preview-canvas { z-index: 2; cursor: crosshair; }
    .status { font-weight: bold; color: #28a745; }
  </style>
</head>
<body>
  <h1>Interactive 2-User Workspace</h1>

  <div id="session-info">
    <p>Session ID: <span id="room-display">Generating...</span></p>
    <p>You are: <span id="user-display" class="status">Connecting...</span> | Active Users: <span id="user-count">0</span>/2</p>
  </div>

  <div id="toolbar">
    <div class="tool-group">
      <button class="tool-btn active" data-tool="pen">Pen</button>
      <button class="tool-btn" data-tool="eraser">Eraser</button>
      <button class="tool-btn" data-tool="line">Line</button>
      <button class="tool-btn" data-tool="rect">Rectangle</button>
      <button class="tool-btn" data-tool="circle">Circle</button>
      <button class="tool-btn" data-tool="text">Text</button>
    </div>

    <label for="color">Color:</label>
    <input type="color" id="color" value="#000000">

    <label for="size">Size:</label>
    <input type="range" id="size" min="1" max="50" value="3">

    <button id="clear-btn">Clear Canvas</button>
  </div>

  <div id="canvas-container">
    <canvas id="drawing-canvas" width="700" height="450"></canvas>
    <canvas id="preview-canvas" width="700" height="450"></canvas>
  </div>

  <script>
    const canvas = document.getElementById('drawing-canvas');
    const ctx = canvas.getContext('2d');
    const previewCanvas = document.getElementById('preview-canvas');
    const previewCtx = previewCanvas.getContext('2d');

    const roomDisplay = document.getElementById('room-display');
    const userDisplay = document.getElementById('user-display');
    const userCount = document.getElementById('user-count');
    const colorInput = document.getElementById('color');
    const sizeInput = document.getElementById('size');
    const clearBtn = document.getElementById('clear-btn');
    const toolButtons = document.querySelectorAll('.tool-btn');

    let currentTool = 'pen';

    toolButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        toolButtons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentTool = btn.dataset.tool;
      });
    });

    const urlParams = new URLSearchParams(window.location.search);
    let roomId = urlParams.get('room');

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    let isDrawing = false;
    let startX = 0, startY = 0;
    let lastX = 0, lastY = 0;

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'create_or_join', roomId: roomId }));
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'joined') {
        roomId = data.roomId;
        roomDisplay.textContent = roomId;
        userDisplay.textContent = data.userLabel;
        userCount.textContent = data.userCount;

        const newUrl = `${window.location.pathname}?room=${roomId}`;
        window.history.pushState({ path: newUrl }, '', newUrl);
      }

      if (data.type === 'user_joined' || data.type === 'user_left') {
        userCount.textContent = data.userCount;
      }

      if (data.type === 'draw') {
        drawLine(data.x0, data.y0, data.x1, data.y1, data.color, data.size, false);
      }

      if (data.type === 'erase') {
        eraseArea(data.x, data.y, data.size, false);
      }

      if (data.type === 'shape') {
        drawShape(data.shape, data.x0, data.y0, data.x1, data.y1, data.color, data.size, ctx, false);
      }

      if (data.type === 'text') {
        drawText(data.text, data.x, data.y, data.color, data.size, false);
      }

      if (data.type === 'clear') {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
      }

      if (data.type === 'error') {
        alert(data.message);
      }
    };

    function drawLine(x0, y0, x1, y1, color, size, emit = true) {
      ctx.beginPath();
      ctx.moveTo(x0, y0);
      ctx.lineTo(x1, y1);
      ctx.strokeStyle = color;
      ctx.lineWidth = size;
      ctx.lineCap = 'round';
      ctx.stroke();
      ctx.closePath();

      if (emit && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'draw', x0, y0, x1, y1, color, size }));
      }
    }

    function eraseArea(x, y, size, emit = true) {
      ctx.clearRect(x - size / 2, y - size / 2, size, size);
      if (emit && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'erase', x, y, size }));
      }
    }

    function drawShape(shape, x0, y0, x1, y1, color, size, context = ctx, emit = true) {
      context.beginPath();
      context.strokeStyle = color;
      context.lineWidth = size;

      if (shape === 'line') {
        context.moveTo(x0, y0);
        context.lineTo(x1, y1);
      } else if (shape === 'rect') {
        context.rect(x0, y0, x1 - x0, y1 - y0);
      } else if (shape === 'circle') {
        const radius = Math.sqrt(Math.pow(x1 - x0, 2) + Math.pow(y1 - y0, 2));
        context.arc(x0, y0, radius, 0, 2 * Math.PI);
      }
      context.stroke();
      context.closePath();

      if (emit && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'shape', shape, x0, y0, x1, y1, color, size }));
      }
    }

    function drawText(text, x, y, color, size, emit = true) {
      ctx.fillStyle = color;
      ctx.font = `${Math.max(12, size * 4)}px sans-serif`;
      ctx.fillText(text, x, y);

      if (emit && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'text', text, x, y, color, size }));
      }
    }

    previewCanvas.addEventListener('mousedown', (e) => {
      const x = e.offsetX;
      const y = e.offsetY;

      if (currentTool === 'text') {
        const text = prompt('Enter your text:');
        if (text) {
          drawText(text, x, y, colorInput.value, sizeInput.value, true);
        }
        return;
      }

      isDrawing = true;
      startX = x;
      startY = y;
      lastX = x;
      lastY = y;

      if (currentTool === 'eraser') {
        eraseArea(x, y, sizeInput.value, true);
      }
    });

    previewCanvas.addEventListener('mousemove', (e) => {
      if (!isDrawing) return;
      const currentX = e.offsetX;
      const currentY = e.offsetY;
      const size = sizeInput.value;
      const color = colorInput.value;

      if (currentTool === 'pen') {
        drawLine(lastX, lastY, currentX, currentY, color, size, true);
        [lastX, lastY] = [currentX, currentY];
      } else if (currentTool === 'eraser') {
        eraseArea(currentX, currentY, size, true);
      } else if (['line', 'rect', 'circle'].includes(currentTool)) {
        previewCtx.clearRect(0, 0, previewCanvas.width, previewCanvas.height);
        drawShape(currentTool, startX, startY, currentX, currentY, color, size, previewCtx, false);
      }
    });

    previewCanvas.addEventListener('mouseup', (e) => {
      if (!isDrawing) return;
      isDrawing = false;

      if (['line', 'rect', 'circle'].includes(currentTool)) {
        previewCtx.clearRect(0, 0, previewCanvas.width, previewCanvas.height);
        drawShape(currentTool, startX, startY, e.offsetX, e.offsetY, colorInput.value, sizeInput.value, ctx, true);
      }
    });

    previewCanvas.addEventListener('mouseout', () => {
      if (isDrawing && ['line', 'rect', 'circle'].includes(currentTool)) {
        previewCtx.clearRect(0, 0, previewCanvas.width, previewCanvas.height);
      }
      isDrawing = false;
    });

    clearBtn.addEventListener('click', () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      previewCtx.clearRect(0, 0, previewCanvas.width, previewCanvas.height);
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'clear' }));
      }
    });
  </script>
</body>
</html>"""


@app.get("/")
async def get():
    return HTMLResponse(content=HTML_CONTENT)


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