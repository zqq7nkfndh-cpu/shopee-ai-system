import http from "http";
import express, { type Express, type Request, type Response } from "express";
import cors from "cors";
import pinoHttp from "pino-http";
import router from "./routes";
import { logger } from "./lib/logger";

const STREAMLIT_PORT = 5000;

const app: Express = express();

app.use(
  pinoHttp({
    logger,
    autoLogging: { ignore: (req) => !req.url?.startsWith("/api") },
    serializers: {
      req(req) {
        return {
          id: req.id,
          method: req.method,
          url: req.url?.split("?")[0],
        };
      },
      res(res) {
        return {
          statusCode: res.statusCode,
        };
      },
    },
  }),
);
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use("/api", router);

// Proxy everything else to Streamlit, stripping iframe-blocking headers
app.use("/", (req: Request, res: Response) => {
  const options: http.RequestOptions = {
    hostname: "127.0.0.1",
    port: STREAMLIT_PORT,
    path: req.url,
    method: req.method,
    headers: { ...req.headers, host: `127.0.0.1:${STREAMLIT_PORT}` },
  };

  const proxy = http.request(options, (proxyRes) => {
    const headers = { ...proxyRes.headers };
    delete headers["x-frame-options"];
    delete headers["content-security-policy"];
    res.writeHead(proxyRes.statusCode ?? 502, headers);
    proxyRes.pipe(res, { end: true });
  });

  proxy.on("error", () => {
    if (!res.headersSent) {
      res.status(502).send(
        "<html><body><p>Streamlit is starting — please wait a moment and refresh.</p></body></html>",
      );
    }
  });

  req.pipe(proxy, { end: true });
});

export default app;
