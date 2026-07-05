import http from "http";
import net from "net";
import app from "./app";
import { logger } from "./lib/logger";

const rawPort = process.env["PORT"];

if (!rawPort) {
  throw new Error(
    "PORT environment variable is required but was not provided.",
  );
}

const port = Number(rawPort);

if (Number.isNaN(port) || port <= 0) {
  throw new Error(`Invalid PORT value: "${rawPort}"`);
}

const STREAMLIT_PORT = 5000;

const server = http.createServer(app);

// WebSocket proxy — forward upgrade requests to Streamlit
server.on("upgrade", (req, socket, head) => {
  const target = net.connect(STREAMLIT_PORT, "127.0.0.1", () => {
    const headers = Object.entries(req.headers)
      .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : v}`)
      .join("\r\n");
    target.write(
      `${req.method} ${req.url} HTTP/1.1\r\n${headers}\r\n\r\n`,
    );
    if (head && head.length > 0) target.write(head);
  });

  target.on("error", () => { try { socket.destroy(); } catch (_) {} });
  socket.on("error", () => { try { target.destroy(); } catch (_) {} });
  target.pipe(socket);
  socket.pipe(target);
});

server.listen(port, () => {
  logger.info({ port }, "Server listening");
});
