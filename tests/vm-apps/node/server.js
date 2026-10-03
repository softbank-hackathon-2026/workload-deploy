// Smallest Node.js web app for the on-prem playbook check (validate.yml). Reads PORT like a real deployed app.
const http = require("node:http");

http
  .createServer((req, res) => {
    const ok = req.url === "/" || req.url === "/health";
    res.writeHead(ok ? 200 : 404, { "Content-Type": "application/json" });
    res.end(ok ? JSON.stringify({ status: "ok", runtime: "node" }) : "{}");
  })
  .listen(Number(process.env.PORT) || 8080);
